from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.addresses.models import Address
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant

from . import services
from .models import ServiceableArea

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919400000001", name="Cust")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def ops_client(db):
    ops = User.objects.create_user(phone="+919400000002", name="Ops", role=User.Role.OPS)
    client = APIClient()
    client.force_authenticate(user=ops)
    return client


def _address(user, pincode="411001", lat=None, lng=None):
    return Address.objects.create(
        user=user, address_line="1 Lane", city="Pune", state="MH",
        pincode=pincode, latitude=lat, longitude=lng,
    )


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
def test_fail_open_when_no_areas(db):
    serviceable, area = services.check("999999")
    assert serviceable is True
    assert area is None


def test_serviceable_pincode(db):
    ServiceableArea.objects.create(pincode="411001", is_active=True)
    assert services.check("411001")[0] is True
    assert services.check("560001")[0] is False


def test_inactive_only_areas_fail_open(db):
    ServiceableArea.objects.create(pincode="411001", is_active=False)
    # No *active* areas → still serving everywhere.
    assert services.check("560001")[0] is True


def test_geofence_inside_and_outside(db):
    ServiceableArea.objects.create(
        pincode="411001", is_active=True,
        center_lat=Decimal("18.520000"), center_lng=Decimal("73.856700"),
        radius_km=Decimal("5.00"),
    )
    # ~1 km away → inside
    assert services.check("411001", 18.5250, 73.8567)[0] is True
    # ~50 km away → outside
    assert services.check("411001", 19.0000, 74.0000)[0] is False


def test_is_serviceable_address(user):
    ServiceableArea.objects.create(pincode="411001", is_active=True)
    assert services.is_serviceable(_address(user, "411001")) is True
    assert services.is_serviceable(_address(user, "560001")) is False


def test_disabled_enforcement(db, settings):
    settings.SERVICEABILITY_ENFORCED = False
    ServiceableArea.objects.create(pincode="411001", is_active=True)
    assert services.check("560001")[0] is True


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_check_endpoint_is_public(db):
    ServiceableArea.objects.create(pincode="411001", is_active=True, delivery_eta_minutes=30)
    client = APIClient()
    response = client.get(reverse("serviceability-check"), {"pincode": "411001"})
    assert response.status_code == 200
    assert response.data["serviceable"] is True
    assert response.data["area"]["delivery_eta_minutes"] == 30


def test_check_endpoint_not_serviceable(db):
    ServiceableArea.objects.create(pincode="411001", is_active=True)
    response = APIClient().get(reverse("serviceability-check"), {"pincode": "560001"})
    assert response.data["serviceable"] is False
    assert response.data["area"] is None


def test_check_endpoint_requires_param(db):
    assert APIClient().get(reverse("serviceability-check")).status_code == 400


def test_ops_can_create_area(ops_client):
    response = ops_client.post(
        reverse("serviceable-area-list"),
        {"pincode": "411045", "area_name": "Baner", "city": "Pune"},
        format="json",
    )
    assert response.status_code == 201


def test_customer_cannot_manage_areas(auth_client):
    response = auth_client.post(
        reverse("serviceable-area-list"), {"pincode": "411045"}, format="json"
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #
def test_checkout_blocked_for_unserviceable_address(auth_client, user):
    ServiceableArea.objects.create(pincode="411001", is_active=True)
    category = Category.objects.create(name="Milk")
    product = Product.objects.create(category=category, name="Milk")
    variant = ProductVariant.objects.create(
        product=product, label="500 ml", sku="MILK-500", price=Decimal("30"), mrp=Decimal("32"), stock=10
    )
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, variant=variant, quantity=1)
    address = _address(user, pincode="560001")  # not served

    response = auth_client.post(reverse("order-checkout"), {"address_id": address.id})
    assert response.status_code == 400
    assert "deliver" in response.data["error"].lower()
