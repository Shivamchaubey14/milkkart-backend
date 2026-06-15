from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.addresses.models import Address
from apps.orders.models import Order
from apps.payments import gateway
from apps.payments.models import Payment

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Test User")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def address(user):
    return Address.objects.create(
        user=user,
        label="home",
        address_line="42 Dairy Lane",
        city="Mumbai",
        state="Maharashtra",
        pincode="400001",
        is_default=True,
    )


@pytest.fixture
def order(user, address):
    return Order.objects.create(
        user=user,
        total=Decimal("80.00"),
        address=address,
        address_snapshot="42 Dairy Lane, Mumbai",
    )


@pytest.mark.django_db
class TestPaymentModel:
    def test_str(self, order, user):
        payment = Payment.objects.create(
            order=order, user=user, method=Payment.Method.COD, amount=order.total
        )
        assert "created" in str(payment)

    def test_default_status(self, order, user):
        payment = Payment.objects.create(
            order=order, user=user, method=Payment.Method.ONLINE, amount=order.total
        )
        assert payment.status == Payment.Status.CREATED
        assert payment.is_paid is False


@pytest.mark.django_db
class TestGateway:
    def test_signature_round_trip(self):
        sig = gateway.sign("order_abc", "pay_xyz")
        assert gateway.verify_signature("order_abc", "pay_xyz", sig)

    def test_bad_signature_rejected(self):
        assert not gateway.verify_signature("order_abc", "pay_xyz", "deadbeef")

    def test_empty_signature_rejected(self):
        assert not gateway.verify_signature("order_abc", "pay_xyz", "")

    def test_create_order_converts_to_paise(self):
        result = gateway.create_gateway_order(Decimal("80.00"), receipt="r1")
        assert result["amount"] == 8000
        assert result["currency"] == "INR"
        assert result["id"].startswith("order_")


@pytest.mark.django_db
class TestInitiatePayment:
    def test_cod_confirms_order(self, auth_client, order):
        response = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "cod"},
        )
        assert response.status_code == 201
        assert response.data["method"] == "cod"
        assert response.data["status"] == "pending"
        order.refresh_from_db()
        assert order.status == Order.Status.CONFIRMED

    def test_online_creates_gateway_order(self, auth_client, order):
        response = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "online"},
        )
        assert response.status_code == 201
        assert response.data["status"] == "created"
        assert response.data["gateway"]["order_id"].startswith("order_")
        assert response.data["gateway"]["amount"] == 8000
        # Online payment leaves the order pending until verification.
        order.refresh_from_db()
        assert order.status == Order.Status.PENDING

    def test_unknown_order_rejected(self, auth_client):
        response = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": "00000000-0000-0000-0000-000000000000", "method": "cod"},
        )
        assert response.status_code == 400

    def test_other_users_order_rejected(self, auth_client, order):
        other = User.objects.create_user(phone="+919876543299", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other)
        response = other_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "cod"},
        )
        assert response.status_code == 400

    def test_non_pending_order_rejected(self, auth_client, order):
        order.status = Order.Status.DELIVERED
        order.save()
        response = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "cod"},
        )
        assert response.status_code == 400

    def test_duplicate_paid_payment_rejected(self, auth_client, order, user):
        Payment.objects.create(
            order=order, user=user, method=Payment.Method.COD,
            status=Payment.Status.SUCCESS, amount=order.total,
        )
        response = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "cod"},
        )
        assert response.status_code == 400

    def test_invalid_method_rejected(self, auth_client, order):
        response = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "crypto"},
        )
        assert response.status_code == 400

    def test_unauthenticated(self, order):
        client = APIClient()
        response = client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "cod"},
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestWalletPayment:
    def test_pay_with_wallet(self, auth_client, order, user):
        from apps.wallet.models import WalletTransaction, get_or_create_wallet

        wallet = get_or_create_wallet(user)
        wallet.credit(Decimal("200"), WalletTransaction.Type.TOPUP)

        response = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "wallet"},
        )
        assert response.status_code == 201
        assert response.data["status"] == "success"

        wallet.refresh_from_db()
        assert wallet.balance == Decimal("120.00")  # 200 - 80
        order.refresh_from_db()
        assert order.status == Order.Status.CONFIRMED

    def test_pay_with_wallet_insufficient(self, auth_client, order, user):
        from apps.wallet.models import get_or_create_wallet

        get_or_create_wallet(user)  # balance 0
        response = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "wallet"},
        )
        assert response.status_code == 400
        assert "insufficient" in response.data["error"].lower()
        order.refresh_from_db()
        assert order.status == Order.Status.PENDING


@pytest.mark.django_db
class TestVerifyPayment:
    def _initiate_online(self, auth_client, order):
        resp = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "online"},
        )
        return resp.data["gateway"]["order_id"]

    def test_verify_success(self, auth_client, order):
        gw_order_id = self._initiate_online(auth_client, order)
        gw_payment_id = "pay_123456"
        signature = gateway.sign(gw_order_id, gw_payment_id)
        response = auth_client.post(
            reverse("payment-verify"),
            {
                "gateway_order_id": gw_order_id,
                "gateway_payment_id": gw_payment_id,
                "gateway_signature": signature,
            },
        )
        assert response.status_code == 200
        assert response.data["status"] == "success"
        assert response.data["is_paid"] is True
        order.refresh_from_db()
        assert order.status == Order.Status.CONFIRMED

    def test_verify_bad_signature_fails_payment(self, auth_client, order):
        gw_order_id = self._initiate_online(auth_client, order)
        response = auth_client.post(
            reverse("payment-verify"),
            {
                "gateway_order_id": gw_order_id,
                "gateway_payment_id": "pay_123456",
                "gateway_signature": "tampered",
            },
        )
        assert response.status_code == 400
        payment = Payment.objects.get(gateway_order_id=gw_order_id)
        assert payment.status == Payment.Status.FAILED
        order.refresh_from_db()
        assert order.status == Order.Status.PENDING

    def test_verify_unknown_order_rejected(self, auth_client):
        response = auth_client.post(
            reverse("payment-verify"),
            {
                "gateway_order_id": "order_missing",
                "gateway_payment_id": "pay_1",
                "gateway_signature": "x",
            },
        )
        assert response.status_code == 400

    def test_verify_is_idempotent_on_success(self, auth_client, order):
        gw_order_id = self._initiate_online(auth_client, order)
        gw_payment_id = "pay_123456"
        signature = gateway.sign(gw_order_id, gw_payment_id)
        payload = {
            "gateway_order_id": gw_order_id,
            "gateway_payment_id": gw_payment_id,
            "gateway_signature": signature,
        }
        first = auth_client.post(reverse("payment-verify"), payload)
        second = auth_client.post(reverse("payment-verify"), payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.data["status"] == "success"


@pytest.mark.django_db
class TestPaymentDetail:
    def test_detail(self, auth_client, order):
        auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "cod"},
        )
        response = auth_client.get(
            reverse("payment-detail", kwargs={"order_number": str(order.order_number)})
        )
        assert response.status_code == 200
        assert response.data["method"] == "cod"

    def test_detail_not_found(self, auth_client, order):
        response = auth_client.get(
            reverse("payment-detail", kwargs={"order_number": str(order.order_number)})
        )
        assert response.status_code == 404

    def test_other_user_cannot_view(self, auth_client, order):
        auth_client.post(
            reverse("payment-initiate"),
            {"order_number": str(order.order_number), "method": "cod"},
        )
        other = User.objects.create_user(phone="+919876543299", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other)
        response = other_client.get(
            reverse("payment-detail", kwargs={"order_number": str(order.order_number)})
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestPaymentTasks:
    def test_send_receipt(self, order, user):
        from apps.payments.tasks import send_payment_receipt

        payment = Payment.objects.create(
            order=order, user=user, method=Payment.Method.COD,
            status=Payment.Status.PENDING, amount=order.total,
        )
        result = send_payment_receipt(payment.id)
        assert result["status"] == "receipt_sent"

    def test_receipt_missing_payment(self):
        from apps.payments.tasks import send_payment_receipt

        assert send_payment_receipt(99999) is None

    def test_process_refund(self, order, user):
        from apps.payments.tasks import process_refund

        payment = Payment.objects.create(
            order=order, user=user, method=Payment.Method.ONLINE,
            status=Payment.Status.REFUNDED, amount=order.total,
            gateway_payment_id="pay_123456",
        )
        result = process_refund(payment.id)
        assert result["status"] == "refund_processed"
        assert result["refund_id"].startswith("rfnd_")

    def test_refund_missing_payment(self):
        from apps.payments.tasks import process_refund

        assert process_refund(99999) is None


# --------------------------------------------------------------------------- #
# Gateway backend selection & webhooks
# --------------------------------------------------------------------------- #
import hashlib  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402

from django.conf import settings  # noqa: E402

from apps.payments.models import PaymentWebhookEvent  # noqa: E402
from apps.wallet.models import WalletTopup, get_or_create_wallet  # noqa: E402


def _sign_body(body):
    return hmac.new(
        settings.PAYMENT_WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()


def _post_webhook(event, event_id="evt_1", signature=None):
    body = json.dumps(event)
    sig = signature if signature is not None else _sign_body(body)
    return APIClient().post(
        reverse("payment-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sig,
        HTTP_X_RAZORPAY_EVENT_ID=event_id,
    )


def _captured_event(order_id, payment_id="pay_1"):
    return {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}},
    }


@pytest.mark.django_db
class TestGatewayBackend:
    def test_webhook_signature_round_trip(self):
        body = '{"event":"x"}'
        assert gateway.verify_webhook_signature(body, _sign_body(body))

    def test_webhook_signature_rejected(self):
        assert not gateway.verify_webhook_signature('{"event":"x"}', "bad")


@pytest.mark.django_db
class TestWebhook:
    def test_invalid_signature_rejected(self):
        response = _post_webhook(_captured_event("order_x"), signature="bad")
        assert response.status_code == 400

    def test_capture_confirms_order_payment(self, order, user):
        Payment.objects.create(
            order=order, user=user, method=Payment.Method.ONLINE,
            status=Payment.Status.CREATED, amount=order.total, gateway_order_id="order_x",
        )
        response = _post_webhook(_captured_event("order_x"), event_id="evt_cap")
        assert response.status_code == 200
        order.refresh_from_db()
        payment = order.payment
        assert payment.status == Payment.Status.SUCCESS
        assert payment.gateway_payment_id == "pay_1"
        assert order.status == Order.Status.CONFIRMED

    def test_capture_is_idempotent(self, order, user):
        Payment.objects.create(
            order=order, user=user, method=Payment.Method.ONLINE,
            status=Payment.Status.CREATED, amount=order.total, gateway_order_id="order_x",
        )
        first = _post_webhook(_captured_event("order_x"), event_id="evt_dup")
        second = _post_webhook(_captured_event("order_x"), event_id="evt_dup")
        assert first.data["status"] == "payment_captured"
        assert second.data["status"] == "duplicate"
        assert PaymentWebhookEvent.objects.filter(event_id="evt_dup").count() == 1

    def test_capture_credits_wallet_topup_once(self, user):
        wallet = get_or_create_wallet(user)
        WalletTopup.objects.create(
            wallet=wallet, amount=Decimal("100.00"),
            status=WalletTopup.Status.CREATED, gateway_order_id="order_top",
        )
        _post_webhook(_captured_event("order_top", "pay_top"), event_id="evt_top")
        wallet.refresh_from_db()
        assert wallet.balance == Decimal("100.00")
        # Replay must not double-credit.
        _post_webhook(_captured_event("order_top", "pay_top"), event_id="evt_top")
        wallet.refresh_from_db()
        assert wallet.balance == Decimal("100.00")

    def test_payment_failed_event(self, order, user):
        Payment.objects.create(
            order=order, user=user, method=Payment.Method.ONLINE,
            status=Payment.Status.CREATED, amount=order.total, gateway_order_id="order_f",
        )
        event = {
            "event": "payment.failed",
            "payload": {"payment": {"entity": {"id": "pay_f", "order_id": "order_f"}}},
        }
        _post_webhook(event, event_id="evt_fail")
        order.payment.refresh_from_db()
        assert order.payment.status == Payment.Status.FAILED

    def test_refund_processed_event(self, order, user):
        Payment.objects.create(
            order=order, user=user, method=Payment.Method.ONLINE,
            status=Payment.Status.SUCCESS, amount=order.total,
            gateway_order_id="order_r", gateway_payment_id="pay_r",
        )
        event = {
            "event": "refund.processed",
            "payload": {"refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_r"}}},
        }
        _post_webhook(event, event_id="evt_refund")
        order.payment.refresh_from_db()
        assert order.payment.status == Payment.Status.REFUNDED

    def test_unmatched_order_is_acknowledged(self):
        response = _post_webhook(_captured_event("order_missing"), event_id="evt_miss")
        assert response.status_code == 200
        assert response.data["status"] == "unmatched"
