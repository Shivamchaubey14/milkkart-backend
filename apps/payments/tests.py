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
