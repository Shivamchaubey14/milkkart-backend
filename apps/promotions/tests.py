from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import Order
from apps.promotions.models import Coupon, CouponRedemption

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Test User")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_coupon(**kwargs):
    now = timezone.now()
    defaults = dict(
        code="SAVE20",
        discount_type=Coupon.DiscountType.FLAT,
        value=Decimal("20"),
        min_order_value=Decimal("0"),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    defaults.update(kwargs)
    return Coupon.objects.create(**defaults)


@pytest.fixture
def variant(db):
    category = Category.objects.create(name="Milk")
    product = Product.objects.create(category=category, name="Full Cream Milk")
    return ProductVariant.objects.create(
        product=product, label="1 L", sku="fcm-1l",
        price=Decimal("60.00"), mrp=Decimal("65.00"), stock=20, is_default=True,
    )


@pytest.mark.django_db
class TestCouponModel:
    def test_code_uppercased(self, db):
        coupon = make_coupon(code="save20")
        assert coupon.code == "SAVE20"

    def test_flat_discount(self, db):
        coupon = make_coupon(discount_type=Coupon.DiscountType.FLAT, value=Decimal("20"))
        assert coupon.calculate_discount(Decimal("100")) == Decimal("20.00")

    def test_percent_discount(self, db):
        coupon = make_coupon(discount_type=Coupon.DiscountType.PERCENT, value=Decimal("10"))
        assert coupon.calculate_discount(Decimal("200")) == Decimal("20.00")

    def test_percent_discount_capped(self, db):
        coupon = make_coupon(
            discount_type=Coupon.DiscountType.PERCENT, value=Decimal("10"), max_discount=Decimal("15")
        )
        assert coupon.calculate_discount(Decimal("200")) == Decimal("15.00")

    def test_discount_never_exceeds_subtotal(self, db):
        coupon = make_coupon(discount_type=Coupon.DiscountType.FLAT, value=Decimal("200"))
        assert coupon.calculate_discount(Decimal("50")) == Decimal("50.00")


@pytest.mark.django_db
class TestCouponEligibility:
    def test_eligible(self, user):
        coupon = make_coupon(min_order_value=Decimal("50"))
        ok, reason = coupon.check_eligibility(user, Decimal("100"))
        assert ok is True and reason is None

    def test_inactive(self, user):
        coupon = make_coupon(is_active=False)
        ok, reason = coupon.check_eligibility(user, Decimal("100"))
        assert ok is False and "active" in reason.lower()

    def test_not_yet_valid(self, user):
        now = timezone.now()
        coupon = make_coupon(valid_from=now + timedelta(days=1), valid_until=now + timedelta(days=2))
        ok, reason = coupon.check_eligibility(user, Decimal("100"))
        assert ok is False and "not yet" in reason.lower()

    def test_expired(self, user):
        now = timezone.now()
        coupon = make_coupon(valid_from=now - timedelta(days=2), valid_until=now - timedelta(days=1))
        ok, reason = coupon.check_eligibility(user, Decimal("100"))
        assert ok is False and "expired" in reason.lower()

    def test_below_min_order(self, user):
        coupon = make_coupon(min_order_value=Decimal("150"))
        ok, reason = coupon.check_eligibility(user, Decimal("100"))
        assert ok is False and "₹150" in reason

    def test_global_usage_limit(self, user):
        coupon = make_coupon(usage_limit=5)
        coupon.times_used = 5
        coupon.save()
        ok, reason = coupon.check_eligibility(user, Decimal("100"))
        assert ok is False and "usage limit" in reason.lower()

    def test_per_user_limit(self, user):
        coupon = make_coupon(per_user_limit=1)
        CouponRedemption.objects.create(coupon=coupon, user=user, discount_amount=Decimal("20"))
        ok, reason = coupon.check_eligibility(user, Decimal("100"))
        assert ok is False and "already used" in reason.lower()

    def test_first_order_only_blocks_returning_user(self, user):
        coupon = make_coupon(first_order_only=True)
        Order.objects.create(user=user, total=Decimal("100"), address_snapshot="x")
        ok, reason = coupon.check_eligibility(user, Decimal("100"))
        assert ok is False and "first order" in reason.lower()

    def test_first_order_only_allows_new_user(self, user):
        coupon = make_coupon(first_order_only=True)
        ok, _ = coupon.check_eligibility(user, Decimal("100"))
        assert ok is True


@pytest.mark.django_db
class TestCouponListAPI:
    def _cart(self, user, variant, qty):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=variant, quantity=qty)
        return cart

    def test_lists_active_coupons_with_eligibility(self, auth_client, user, variant):
        self._cart(user, variant, 2)  # subtotal 120
        make_coupon(code="OK", min_order_value=Decimal("100"))
        make_coupon(code="TOOBIG", min_order_value=Decimal("500"))
        response = auth_client.get(reverse("coupon-list"))
        assert response.status_code == 200
        by_code = {c["code"]: c for c in response.data}
        assert by_code["OK"]["is_eligible"] is True
        assert Decimal(by_code["OK"]["potential_discount"]) == Decimal("20.00")
        assert by_code["TOOBIG"]["is_eligible"] is False
        assert by_code["TOOBIG"]["potential_discount"] is None

    def test_excludes_expired(self, auth_client, user, variant):
        now = timezone.now()
        make_coupon(code="OLD", valid_from=now - timedelta(days=5), valid_until=now - timedelta(days=1))
        response = auth_client.get(reverse("coupon-list"))
        assert all(c["code"] != "OLD" for c in response.data)

    def test_requires_auth(self):
        response = APIClient().get(reverse("coupon-list"))
        assert response.status_code == 401
