import pytest
from django.core.management import call_command
from django.test import RequestFactory
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductVariant
from apps.core.views import health_check
from apps.orders.models import DeliverySlot


class TestHealthCheck:
    def test_health_check_returns_ok(self):
        factory = RequestFactory()
        request = factory.get("/api/v1/health/")
        response = health_check(request)
        assert response.status_code == 200
        assert response.data == {"status": "ok"}


class TestExceptionHandler:
    def test_validation_error_format(self):
        client = APIClient()
        response = client.post("/api/v1/auth/otp/send/", {})
        assert response.status_code == 400
        assert "status_code" in response.data
        assert "errors" in response.data
        assert response.data["status_code"] == 400

    def test_auth_error_format(self):
        client = APIClient()
        response = client.get("/api/v1/auth/me/")
        assert response.status_code == 401
        assert response.data["status_code"] == 401


@pytest.mark.django_db
class TestSeedCatalogCommand:
    def test_seed_catalog(self):
        call_command("seed_catalog")
        assert Category.objects.count() == 6
        assert Product.objects.count() == 22
        assert ProductVariant.objects.count() == 29

    def test_seed_catalog_idempotent(self):
        call_command("seed_catalog")
        call_command("seed_catalog")
        assert Category.objects.count() == 6
        assert Product.objects.count() == 22
        assert ProductVariant.objects.count() == 29


@pytest.mark.django_db
class TestSeedCouponsCommand:
    def test_seed_coupons(self):
        from apps.promotions.models import Coupon

        call_command("seed_coupons")
        assert Coupon.objects.count() == 3

    def test_seed_coupons_idempotent(self):
        from apps.promotions.models import Coupon

        call_command("seed_coupons")
        call_command("seed_coupons")
        assert Coupon.objects.count() == 3


@pytest.mark.django_db
class TestSeedSlotsCommand:
    def test_seed_slots(self):
        call_command("seed_slots", "--days=3")
        assert DeliverySlot.objects.count() == 9

    def test_seed_slots_idempotent(self):
        call_command("seed_slots", "--days=3")
        call_command("seed_slots", "--days=3")
        assert DeliverySlot.objects.count() == 9


@pytest.mark.django_db
class TestCreateTestUserCommand:
    def test_create_test_user(self):
        from django.contrib.auth import get_user_model

        call_command("create_test_user")
        User = get_user_model()
        user = User.objects.get(phone="+919999999999")
        assert user.name == "Dev User"
        assert user.addresses.count() == 1
