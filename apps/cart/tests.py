from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cart.billing import compute_bill
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant
from apps.promotions.models import Coupon

User = get_user_model()


def make_coupon(**kwargs):
    now = timezone.now()
    defaults = dict(
        code="FLAT20",
        discount_type=Coupon.DiscountType.FLAT,
        value=Decimal("20"),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    defaults.update(kwargs)
    return Coupon.objects.create(**defaults)


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Test User")


@pytest.fixture
def category(db):
    return Category.objects.create(name="Milk")


@pytest.fixture
def variant(category):
    product = Product.objects.create(category=category, name="Full Cream Milk")
    return ProductVariant.objects.create(
        product=product, label="500 ml", sku="fcm-500",
        price=Decimal("28.00"), mrp=Decimal("30.00"), stock=10, is_default=True,
    )


@pytest.fixture
def variant_b(category):
    product = Product.objects.create(category=category, name="Toned Milk")
    return ProductVariant.objects.create(
        product=product, label="500 ml", sku="tm-500",
        price=Decimal("24.00"), mrp=Decimal("26.00"), stock=5, is_default=True,
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestCartModel:
    def test_str(self, user):
        cart = Cart.objects.create(user=user)
        assert str(cart) == "Cart(+919876543210)"

    def test_total(self, user, variant, variant_b):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=variant, quantity=2)
        CartItem.objects.create(cart=cart, variant=variant_b, quantity=1)
        assert cart.total == Decimal("80.00")

    def test_item_count(self, user, variant):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=variant, quantity=3)
        assert cart.item_count == 1


@pytest.mark.django_db
class TestCartItemModel:
    def test_str(self, user, variant):
        cart = Cart.objects.create(user=user)
        item = CartItem.objects.create(cart=cart, variant=variant, quantity=2)
        assert str(item) == "Full Cream Milk (500 ml) x2"

    def test_subtotal(self, user, variant):
        cart = Cart.objects.create(user=user)
        item = CartItem.objects.create(cart=cart, variant=variant, quantity=3)
        assert item.subtotal == Decimal("84.00")


@pytest.mark.django_db
class TestCartDetailAPI:
    def test_get_empty_cart(self, auth_client):
        response = auth_client.get(reverse("cart-detail"))
        assert response.status_code == 200
        assert response.data["item_count"] == 0

    def test_unauthenticated(self):
        client = APIClient()
        response = client.get(reverse("cart-detail"))
        assert response.status_code == 401


@pytest.mark.django_db
class TestAddToCartAPI:
    def test_add_item(self, auth_client, variant):
        response = auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 2})
        assert response.status_code == 200
        assert response.data["item_count"] == 1
        assert Decimal(response.data["bill"]["subtotal"]) == Decimal("56.00")

    def test_add_same_variant_increments(self, auth_client, variant):
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 2})
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 1})
        response = auth_client.get(reverse("cart-detail"))
        assert response.data["items"][0]["quantity"] == 3

    def test_add_exceeds_stock(self, auth_client, variant):
        response = auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 999})
        assert response.status_code == 400
        assert "stock" in response.data["error"].lower()

    def test_add_invalid_variant(self, auth_client):
        response = auth_client.post(reverse("cart-add"), {"variant_id": 99999, "quantity": 1})
        assert response.status_code == 400


@pytest.mark.django_db
class TestCartItemDetailAPI:
    def test_update_quantity(self, auth_client, variant):
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 1})
        response = auth_client.get(reverse("cart-detail"))
        item_id = response.data["items"][0]["id"]

        response = auth_client.patch(
            reverse("cart-item-detail", kwargs={"item_id": item_id}),
            {"quantity": 5},
        )
        assert response.status_code == 200
        assert response.data["items"][0]["quantity"] == 5

    def test_update_exceeds_stock(self, auth_client, variant):
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 1})
        response = auth_client.get(reverse("cart-detail"))
        item_id = response.data["items"][0]["id"]

        response = auth_client.patch(
            reverse("cart-item-detail", kwargs={"item_id": item_id}),
            {"quantity": 999},
        )
        assert response.status_code == 400

    def test_delete_item(self, auth_client, variant):
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 1})
        response = auth_client.get(reverse("cart-detail"))
        item_id = response.data["items"][0]["id"]

        response = auth_client.delete(reverse("cart-item-detail", kwargs={"item_id": item_id}))
        assert response.status_code == 200
        assert response.data["item_count"] == 0

    def test_not_found(self, auth_client):
        response = auth_client.delete(reverse("cart-item-detail", kwargs={"item_id": 99999}))
        assert response.status_code == 404


@pytest.mark.django_db
class TestBillEngine:
    def test_empty_cart_is_zero(self, user):
        cart = Cart.objects.create(user=user)
        bill = compute_bill(cart)
        assert bill["subtotal"] == Decimal("0.00")
        assert bill["delivery_fee"] == Decimal("0.00")
        assert bill["grand_total"] == Decimal("0.00")

    def test_small_cart_fees_and_tax(self, user, variant, variant_b):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=variant, quantity=2)  # 56
        CartItem.objects.create(cart=cart, variant=variant_b, quantity=1)  # 24
        bill = compute_bill(cart)
        assert bill["subtotal"] == Decimal("80.00")
        assert bill["mrp_savings"] == Decimal("6.00")
        assert bill["delivery_fee"] == Decimal("25.00")  # below free threshold
        assert bill["small_cart_fee"] == Decimal("15.00")  # below small-cart threshold
        assert bill["tax"] == Decimal("6.00")  # 5% of 120
        assert bill["grand_total"] == Decimal("126.00")

    def test_free_delivery_above_threshold(self, user, variant):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=variant, quantity=8)  # 224
        bill = compute_bill(cart)
        assert bill["delivery_fee"] == Decimal("0.00")
        assert bill["small_cart_fee"] == Decimal("0.00")
        assert bill["grand_total"] == Decimal("235.20")  # 224 + 5% tax

    def test_coupon_discount_applied(self, user, variant, variant_b):
        cart = Cart.objects.create(user=user, applied_coupon=make_coupon())
        CartItem.objects.create(cart=cart, variant=variant, quantity=2)
        CartItem.objects.create(cart=cart, variant=variant_b, quantity=1)
        bill = compute_bill(cart)
        assert bill["coupon_code"] == "FLAT20"
        assert bill["coupon_discount"] == Decimal("20.00")
        # (80-20) + 25 + 15 + 5% of 100 = 105.00
        assert bill["grand_total"] == Decimal("105.00")

    def test_ineligible_coupon_ignored(self, user, variant):
        coupon = make_coupon(min_order_value=Decimal("500"))
        cart = Cart.objects.create(user=user, applied_coupon=coupon)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)  # 28
        bill = compute_bill(cart)
        assert bill["coupon_code"] is None
        assert bill["coupon_discount"] == Decimal("0.00")


@pytest.mark.django_db
class TestCartCouponAPI:
    def test_apply_coupon(self, auth_client, user, variant):
        Cart.objects.create(user=user)
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 4})  # 112
        make_coupon(code="FLAT20", min_order_value=Decimal("100"))
        response = auth_client.post(reverse("cart-apply-coupon"), {"code": "flat20"})
        assert response.status_code == 200
        assert response.data["coupon_code"] == "FLAT20"
        assert Decimal(response.data["bill"]["coupon_discount"]) == Decimal("20.00")

    def test_apply_invalid_code(self, auth_client, user, variant):
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 4})
        response = auth_client.post(reverse("cart-apply-coupon"), {"code": "NOPE"})
        assert response.status_code == 400
        assert "invalid" in response.data["error"].lower()

    def test_apply_ineligible_returns_reason(self, auth_client, user, variant):
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 1})  # 28
        make_coupon(code="BIG", min_order_value=Decimal("500"))
        response = auth_client.post(reverse("cart-apply-coupon"), {"code": "BIG"})
        assert response.status_code == 400
        assert "₹500" in response.data["error"]

    def test_remove_coupon(self, auth_client, user, variant):
        auth_client.post(reverse("cart-add"), {"variant_id": variant.id, "quantity": 4})
        make_coupon(code="FLAT20", min_order_value=Decimal("100"))
        auth_client.post(reverse("cart-apply-coupon"), {"code": "FLAT20"})
        response = auth_client.post(reverse("cart-remove-coupon"))
        assert response.status_code == 200
        assert response.data["coupon_code"] is None
        assert Decimal(response.data["bill"]["coupon_discount"]) == Decimal("0.00")
