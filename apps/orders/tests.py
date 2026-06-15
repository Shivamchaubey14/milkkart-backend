from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.addresses.models import Address
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import DeliverySlot, Order
from apps.promotions.models import Coupon, CouponRedemption

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Test User")


@pytest.fixture
def category(db):
    return Category.objects.create(name="Milk")


# `product`/`product_b` fixtures return the sellable ProductVariant (SKU).
@pytest.fixture
def product(category):
    p = Product.objects.create(category=category, name="Full Cream Milk")
    return ProductVariant.objects.create(
        product=p, label="500 ml", sku="fcm-500",
        price=Decimal("28.00"), mrp=Decimal("30.00"), stock=10, is_default=True,
    )


@pytest.fixture
def product_b(category):
    p = Product.objects.create(category=category, name="Toned Milk")
    return ProductVariant.objects.create(
        product=p, label="500 ml", sku="tm-500",
        price=Decimal("24.00"), mrp=Decimal("26.00"), stock=5, is_default=True,
    )


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
def delivery_slot(db):
    return DeliverySlot.objects.create(
        date=date(2026, 6, 15),
        start_time=time(7, 0),
        end_time=time(9, 0),
        capacity=20,
    )


@pytest.fixture
def cart_with_items(user, product, product_b):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, variant=product, quantity=2)
    CartItem.objects.create(cart=cart, variant=product_b, quantity=1)
    return cart


@pytest.mark.django_db
class TestDeliverySlotModel:
    def test_str(self, delivery_slot):
        assert "2026-06-15" in str(delivery_slot)

    def test_available(self, delivery_slot):
        assert delivery_slot.available == 20

    def test_is_full(self, delivery_slot):
        assert not delivery_slot.is_full
        delivery_slot.booked = 20
        assert delivery_slot.is_full


@pytest.mark.django_db
class TestDeliverySlotAPI:
    def test_list_slots(self, auth_client, delivery_slot):
        response = auth_client.get(reverse("delivery-slot-list"))
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_filter_by_date(self, auth_client, delivery_slot):
        response = auth_client.get(reverse("delivery-slot-list"), {"date": "2026-06-15"})
        assert len(response.data) == 1

    def test_filter_excludes_wrong_date(self, auth_client, delivery_slot):
        response = auth_client.get(reverse("delivery-slot-list"), {"date": "2026-01-01"})
        assert len(response.data) == 0

    def test_excludes_full_slots(self, auth_client, delivery_slot):
        delivery_slot.booked = 20
        delivery_slot.save()
        response = auth_client.get(reverse("delivery-slot-list"))
        assert len(response.data) == 0


@pytest.mark.django_db
class TestOrderModel:
    def test_str(self, user, address):
        order = Order.objects.create(user=user, total=Decimal("100.00"), address=address, address_snapshot="test")
        assert "pending" in str(order)

    def test_default_status(self, user, address):
        order = Order.objects.create(user=user, total=Decimal("100.00"), address=address, address_snapshot="test")
        assert order.status == Order.Status.PENDING


@pytest.mark.django_db
class TestCheckoutAPI:
    def test_checkout_success(self, auth_client, cart_with_items, address, product, product_b):
        response = auth_client.post(
            reverse("order-checkout"),
            {"address_id": address.id},
        )
        assert response.status_code == 201
        # subtotal 80 + delivery 25 + small-cart 15 + 5% tax (6.00) = 126.00
        assert Decimal(response.data["subtotal"]) == Decimal("80.00")
        assert Decimal(response.data["total"]) == Decimal("126.00")
        assert "42 Dairy Lane" in response.data["address_snapshot"]
        assert len(response.data["items"]) == 2

        product.refresh_from_db()
        product_b.refresh_from_db()
        assert product.stock == 8
        assert product_b.stock == 4
        assert cart_with_items.items.count() == 0

    def test_checkout_with_delivery_slot(self, auth_client, cart_with_items, address, delivery_slot):
        response = auth_client.post(
            reverse("order-checkout"),
            {"address_id": address.id, "delivery_slot_id": delivery_slot.id},
        )
        assert response.status_code == 201
        assert response.data["delivery_slot"]["id"] == delivery_slot.id
        delivery_slot.refresh_from_db()
        assert delivery_slot.booked == 1

    def test_checkout_full_slot_rejected(self, auth_client, cart_with_items, address, delivery_slot):
        delivery_slot.booked = 20
        delivery_slot.save()
        response = auth_client.post(
            reverse("order-checkout"),
            {"address_id": address.id, "delivery_slot_id": delivery_slot.id},
        )
        assert response.status_code == 400
        assert "full" in response.data["error"].lower()

    def test_checkout_invalid_address(self, auth_client, cart_with_items):
        response = auth_client.post(
            reverse("order-checkout"),
            {"address_id": 99999},
        )
        assert response.status_code == 400
        assert "address" in response.data["error"].lower()

    def test_checkout_other_users_address(self, auth_client, cart_with_items):
        other_user = User.objects.create_user(phone="+919876543211", name="Other")
        other_addr = Address.objects.create(
            user=other_user, label="home", address_line="x", city="x", state="x", pincode="000000"
        )
        response = auth_client.post(reverse("order-checkout"), {"address_id": other_addr.id})
        assert response.status_code == 400

    def test_checkout_empty_cart(self, auth_client, address):
        response = auth_client.post(reverse("order-checkout"), {"address_id": address.id})
        assert response.status_code == 400
        assert "empty" in response.data["error"].lower()

    def test_checkout_insufficient_stock(self, auth_client, user, product, address):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=product, quantity=999)
        response = auth_client.post(reverse("order-checkout"), {"address_id": address.id})
        assert response.status_code == 400
        assert "stock" in response.data["error"].lower()

    def test_checkout_is_oversell_safe_under_race(
        self, auth_client, user, product, address, monkeypatch
    ):
        """A concurrent buyer draining stock after the pre-check must not oversell."""
        from apps.cart.billing import compute_bill as real_compute_bill
        from apps.inventory.models import StockMovement

        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=product, quantity=product.stock)

        # Simulate another order grabbing all the stock between the pre-check and the
        # locked write: compute_bill runs in that window.
        def drain_then_bill(c):
            ProductVariant.objects.filter(pk=product.pk).update(stock=0)
            return real_compute_bill(c)

        monkeypatch.setattr("apps.orders.views.compute_bill", drain_then_bill)

        response = auth_client.post(reverse("order-checkout"), {"address_id": address.id})

        assert response.status_code == 409
        # Order rolled back; no negative stock, no movement, cart intact.
        assert not Order.objects.filter(user=user).exists()
        assert not StockMovement.objects.exists()
        product.refresh_from_db()
        assert product.stock == 0
        assert cart.items.count() == 1

    def test_checkout_missing_address_id(self, auth_client, cart_with_items):
        response = auth_client.post(reverse("order-checkout"), {})
        assert response.status_code == 400

    def test_checkout_unauthenticated(self):
        client = APIClient()
        response = client.post(reverse("order-checkout"), {"address_id": 1})
        assert response.status_code == 401

    def test_checkout_with_notes(self, auth_client, cart_with_items, address):
        response = auth_client.post(
            reverse("order-checkout"),
            {"address_id": address.id, "notes": "Ring the bell"},
        )
        assert response.status_code == 201
        assert response.data["notes"] == "Ring the bell"

    def test_checkout_applies_coupon(self, auth_client, user, cart_with_items, address):
        now = timezone.now()
        coupon = Coupon.objects.create(
            code="FLAT20", discount_type=Coupon.DiscountType.FLAT, value=Decimal("20"),
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        cart_with_items.applied_coupon = coupon
        cart_with_items.save()

        response = auth_client.post(reverse("order-checkout"), {"address_id": address.id})
        assert response.status_code == 201
        # subtotal 80, -20 coupon, +25 delivery +15 small-cart, +5% tax (5.00) = 105.00
        assert Decimal(response.data["discount"]) == Decimal("20.00")
        assert Decimal(response.data["total"]) == Decimal("105.00")
        assert response.data["coupon_code"] == "FLAT20"

        order = Order.objects.get(order_number=response.data["order_number"])
        assert CouponRedemption.objects.filter(coupon=coupon, order=order).count() == 1
        coupon.refresh_from_db()
        assert coupon.times_used == 1
        cart_with_items.refresh_from_db()
        assert cart_with_items.applied_coupon is None


@pytest.mark.django_db
class TestOrderListAPI:
    def test_list_orders(self, auth_client, cart_with_items, address):
        auth_client.post(reverse("order-checkout"), {"address_id": address.id})
        response = auth_client.get(reverse("order-list"))
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_list_empty(self, auth_client):
        response = auth_client.get(reverse("order-list"))
        assert response.status_code == 200
        assert len(response.data) == 0

    def test_user_isolation(self, auth_client, cart_with_items, address):
        auth_client.post(reverse("order-checkout"), {"address_id": address.id})
        other_user = User.objects.create_user(phone="+919876543211", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse("order-list"))
        assert len(response.data) == 0


@pytest.mark.django_db
class TestOrderDetailAPI:
    def test_detail(self, auth_client, cart_with_items, address):
        checkout_resp = auth_client.post(reverse("order-checkout"), {"address_id": address.id})
        order_number = checkout_resp.data["order_number"]
        response = auth_client.get(reverse("order-detail", kwargs={"order_number": order_number}))
        assert response.status_code == 200
        assert len(response.data["items"]) == 2

    def test_not_found(self, auth_client):
        response = auth_client.get(
            reverse("order-detail", kwargs={"order_number": "00000000-0000-0000-0000-000000000000"})
        )
        assert response.status_code == 404

    def test_other_user_cannot_view(self, auth_client, cart_with_items, address):
        checkout_resp = auth_client.post(reverse("order-checkout"), {"address_id": address.id})
        order_number = checkout_resp.data["order_number"]
        other_user = User.objects.create_user(phone="+919876543211", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse("order-detail", kwargs={"order_number": order_number}))
        assert response.status_code == 404


@pytest.mark.django_db
class TestOrderTasks:
    def test_send_order_confirmation(self, user, address):
        from apps.orders.tasks import send_order_confirmation

        order = Order.objects.create(user=user, total=Decimal("100.00"), address=address, address_snapshot="test")
        result = send_order_confirmation(order.id)
        assert result["status"] == "confirmation_sent"

    def test_send_order_status_update(self, user, address):
        from apps.orders.tasks import send_order_status_update

        order = Order.objects.create(user=user, total=Decimal("100.00"), address=address, address_snapshot="test")
        result = send_order_status_update(order.id, "confirmed")
        assert result["new_status"] == "confirmed"

    def test_confirmation_missing_order(self):
        from apps.orders.tasks import send_order_confirmation

        result = send_order_confirmation(99999)
        assert result is None


@pytest.mark.django_db
class TestCancelOrderAPI:
    def _place_order(self, auth_client, address, slot_id=None):
        payload = {"address_id": address.id}
        if slot_id:
            payload["delivery_slot_id"] = slot_id
        resp = auth_client.post(reverse("order-checkout"), payload)
        return resp.data["order_number"]

    def test_cancel_restocks_and_cancels(self, auth_client, cart_with_items, address, product, product_b):
        order_number = self._place_order(auth_client, address)
        product.refresh_from_db()
        assert product.stock == 8  # reserved at checkout

        response = auth_client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        assert response.status_code == 200
        assert response.data["status"] == "cancelled"

        product.refresh_from_db()
        product_b.refresh_from_db()
        assert product.stock == 10  # restocked
        assert product_b.stock == 5

    def test_cancel_frees_delivery_slot(self, auth_client, cart_with_items, address, delivery_slot):
        order_number = self._place_order(auth_client, address, slot_id=delivery_slot.id)
        delivery_slot.refresh_from_db()
        assert delivery_slot.booked == 1

        auth_client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        delivery_slot.refresh_from_db()
        assert delivery_slot.booked == 0

    def test_cancel_refunds_paid_online_order(self, auth_client, cart_with_items, address):
        from apps.payments import gateway
        from apps.payments.models import Payment

        order_number = self._place_order(auth_client, address)
        init = auth_client.post(
            reverse("payment-initiate"),
            {"order_number": order_number, "method": "online"},
        )
        gw_order_id = init.data["gateway"]["order_id"]
        gw_payment_id = "pay_abcdef"
        auth_client.post(
            reverse("payment-verify"),
            {
                "gateway_order_id": gw_order_id,
                "gateway_payment_id": gw_payment_id,
                "gateway_signature": gateway.sign(gw_order_id, gw_payment_id),
            },
        )

        response = auth_client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        assert response.status_code == 200
        payment = Payment.objects.get(order__order_number=order_number)
        assert payment.status == Payment.Status.REFUNDED

    def test_cancel_refunds_wallet_payment_to_wallet(self, auth_client, cart_with_items, address, user):
        from apps.payments.models import Payment
        from apps.wallet.models import WalletTransaction, get_or_create_wallet

        wallet = get_or_create_wallet(user)
        wallet.credit(Decimal("500"), WalletTransaction.Type.TOPUP)

        order_number = self._place_order(auth_client, address)  # subtotal 80 -> total 126
        auth_client.post(
            reverse("payment-initiate"),
            {"order_number": order_number, "method": "wallet"},
        )
        wallet.refresh_from_db()
        assert wallet.balance == Decimal("374.00")  # 500 - 126

        auth_client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        wallet.refresh_from_db()
        assert wallet.balance == Decimal("500.00")  # refunded to wallet
        payment = Payment.objects.get(order__order_number=order_number)
        assert payment.status == Payment.Status.REFUNDED

    def test_cancel_voids_unpaid_cod_payment(self, auth_client, cart_with_items, address):
        from apps.payments.models import Payment

        order_number = self._place_order(auth_client, address)
        auth_client.post(
            reverse("payment-initiate"),
            {"order_number": order_number, "method": "cod"},
        )
        auth_client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        payment = Payment.objects.get(order__order_number=order_number)
        assert payment.status == Payment.Status.FAILED

    def test_cannot_cancel_delivered_order(self, auth_client, cart_with_items, address):
        order_number = self._place_order(auth_client, address)
        order = Order.objects.get(order_number=order_number)
        order.status = Order.Status.DELIVERED
        order.save()
        response = auth_client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        assert response.status_code == 400
        assert "cannot be cancelled" in response.data["error"].lower()

    def test_cannot_cancel_out_for_delivery_order(self, auth_client, cart_with_items, address):
        order_number = self._place_order(auth_client, address)
        order = Order.objects.get(order_number=order_number)
        order.status = Order.Status.OUT_FOR_DELIVERY
        order.save()
        response = auth_client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        assert response.status_code == 400

    def test_cancel_not_found(self, auth_client):
        response = auth_client.post(
            reverse("order-cancel", kwargs={"order_number": "00000000-0000-0000-0000-000000000000"})
        )
        assert response.status_code == 404

    def test_other_user_cannot_cancel(self, auth_client, cart_with_items, address):
        order_number = self._place_order(auth_client, address)
        other_user = User.objects.create_user(phone="+919876543211", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        assert response.status_code == 404

    def test_cancel_unauthenticated(self, auth_client, cart_with_items, address):
        order_number = self._place_order(auth_client, address)
        client = APIClient()
        response = client.post(reverse("order-cancel", kwargs={"order_number": order_number}))
        assert response.status_code == 401
