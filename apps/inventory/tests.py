from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductVariant
from apps.notifications.models import Notification

from . import services
from .models import StockMovement

User = get_user_model()


@pytest.fixture
def variant(db):
    category = Category.objects.create(name="Milk")
    product = Product.objects.create(category=category, name="Full Cream Milk")
    return ProductVariant.objects.create(
        product=product, label="500 ml", sku="MILK-500", price=Decimal("30"), mrp=Decimal("32"), stock=50
    )


@pytest.fixture
def warehouse(db):
    return User.objects.create_user(phone="+919200000001", name="WH", role=User.Role.WAREHOUSE)


@pytest.fixture
def warehouse_client(warehouse):
    client = APIClient()
    client.force_authenticate(user=warehouse)
    return client


@pytest.fixture
def customer_client(db):
    user = User.objects.create_user(phone="+919200000009", name="Cust")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
def test_adjust_stock_decrements_and_records(variant):
    movement = services.adjust_stock(variant, -5, StockMovement.Reason.SALE)
    variant.refresh_from_db()
    assert variant.stock == 45
    assert movement.delta == -5
    assert movement.balance_after == 45


def test_adjust_stock_increment(variant):
    services.adjust_stock(variant, 10, StockMovement.Reason.RESTOCK)
    variant.refresh_from_db()
    assert variant.stock == 60


def test_adjust_stock_oversell_raises_and_is_atomic(variant):
    with pytest.raises(services.OutOfStock):
        services.adjust_stock(variant, -100, StockMovement.Reason.SALE)
    variant.refresh_from_db()
    assert variant.stock == 50
    assert StockMovement.objects.count() == 0


def test_restock_helper(variant):
    services.restock(variant, 20, note="weekly")
    variant.refresh_from_db()
    assert variant.stock == 70
    assert StockMovement.objects.get().reason == StockMovement.Reason.RESTOCK


def test_restock_rejects_non_positive(variant):
    with pytest.raises(ValueError):
        services.restock(variant, 0)


def test_low_stock_variants(variant):
    variant.stock = 3
    variant.save(update_fields=["stock"])
    assert variant in list(services.low_stock_variants())
    assert variant not in list(services.low_stock_variants(threshold=2))


# --------------------------------------------------------------------------- #
# Low-stock alerting
# --------------------------------------------------------------------------- #
def test_crossing_threshold_alerts_ops_staff(variant):
    ops = User.objects.create_user(phone="+919200000002", name="Ops", role=User.Role.OPS)
    variant.stock = 11
    variant.save(update_fields=["stock"])
    services.adjust_stock(variant, -2, StockMovement.Reason.SALE)  # 11 -> 9, crosses 10
    assert Notification.objects.filter(user=ops, title="Low stock").exists()


def test_no_alert_when_above_threshold(variant):
    ops = User.objects.create_user(phone="+919200000003", name="Ops", role=User.Role.OPS)
    services.adjust_stock(variant, -5, StockMovement.Reason.SALE)  # 50 -> 45
    assert not Notification.objects.filter(user=ops, title="Low stock").exists()


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_warehouse_can_restock(warehouse_client, variant):
    url = reverse("stock-restock")
    response = warehouse_client.post(url, {"variant_id": variant.id, "quantity": 25}, format="json")
    assert response.status_code == 201
    variant.refresh_from_db()
    assert variant.stock == 75


def test_customer_cannot_restock(customer_client, variant):
    url = reverse("stock-restock")
    response = customer_client.post(url, {"variant_id": variant.id, "quantity": 25}, format="json")
    assert response.status_code == 403


def test_adjust_damage_reduces_stock(warehouse_client, variant):
    url = reverse("stock-adjust")
    response = warehouse_client.post(
        url, {"variant_id": variant.id, "delta": -4, "reason": "damage"}, format="json"
    )
    assert response.status_code == 201
    variant.refresh_from_db()
    assert variant.stock == 46


def test_adjust_oversell_returns_400(warehouse_client, variant):
    url = reverse("stock-adjust")
    response = warehouse_client.post(
        url, {"variant_id": variant.id, "delta": -999, "reason": "adjustment"}, format="json"
    )
    assert response.status_code == 400


def test_low_stock_report(warehouse_client, variant):
    variant.stock = 2
    variant.save(update_fields=["stock"])
    response = warehouse_client.get(reverse("low-stock"))
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["variants"][0]["sku"] == "MILK-500"


def test_movement_list_filters_by_variant(warehouse_client, variant):
    services.adjust_stock(variant, -1, StockMovement.Reason.SALE)
    response = warehouse_client.get(reverse("stock-movement-list"), {"variant_id": variant.id})
    assert response.status_code == 200
    assert response.data["count"] == 1
