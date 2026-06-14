import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.addresses.models import Address
from apps.catalog.models import Category, Product, ProductVariant
from apps.delivery.models import DeliveryAssignment, DeliveryPartner
from apps.orders.models import Order, OrderItem
from apps.subscriptions.models import Subscription
from apps.support.models import OrderReview

User = get_user_model()


@pytest.fixture
def customer(db):
    return User.objects.create_user(phone="+919300000001", name="Cust")


@pytest.fixture
def ops_client(db):
    user = User.objects.create_user(phone="+919300000002", name="Ops", role=User.Role.OPS)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def variant(db):
    category = Category.objects.create(name="Milk")
    product = Product.objects.create(category=category, name="Full Cream Milk")
    return ProductVariant.objects.create(
        product=product, label="500 ml", sku="MILK-500", price=Decimal("30"), mrp=Decimal("32"), stock=50
    )


def _order(user, total, status=Order.Status.DELIVERED, product="Milk", price="30", qty=2):
    order = Order.objects.create(user=user, status=status, total=Decimal(total))
    OrderItem.objects.create(
        order=order, product_name=product, product_price=Decimal(price), quantity=qty
    )
    return order


# --------------------------------------------------------------------------- #
# Sales & products
# --------------------------------------------------------------------------- #
def test_sales_summary_excludes_cancelled(ops_client, customer):
    _order(customer, "100.00")
    _order(customer, "60.00")
    _order(customer, "999.00", status=Order.Status.CANCELLED)
    response = ops_client.get(reverse("report-sales"))
    assert response.status_code == 200
    assert response.data["orders"] == 2
    assert response.data["revenue"] == "160.00"
    assert response.data["average_order_value"] == "80.00"


def test_top_products_ranked_by_quantity(ops_client, customer):
    _order(customer, "60.00", product="Milk", price="30", qty=5)
    _order(customer, "40.00", product="Butter", price="40", qty=1)
    response = ops_client.get(reverse("report-top-products"))
    assert response.status_code == 200
    assert response.data[0]["product_name"] == "Milk"
    assert response.data[0]["quantity"] == 5


def test_order_status_breakdown(ops_client, customer):
    _order(customer, "10.00", status=Order.Status.DELIVERED)
    _order(customer, "10.00", status=Order.Status.PENDING)
    response = ops_client.get(reverse("report-order-status"))
    assert response.data["delivered"] == 1
    assert response.data["pending"] == 1


# --------------------------------------------------------------------------- #
# Subscriptions & riders
# --------------------------------------------------------------------------- #
def test_subscription_report_counts(ops_client, customer, variant):
    address = Address.objects.create(
        user=customer, address_line="1 Lane", city="Pune", state="MH", pincode="411001"
    )
    today = datetime.date.today()
    Subscription.objects.create(
        user=customer, variant=variant, quantity=1, address=address,
        status=Subscription.Status.ACTIVE, start_date=today,
    )
    Subscription.objects.create(
        user=customer, variant=variant, quantity=1, address=address,
        status=Subscription.Status.CANCELLED, start_date=today,
    )
    response = ops_client.get(reverse("report-subscriptions"))
    assert response.data["active"] == 1
    assert response.data["cancelled"] == 1
    assert response.data["total"] == 2


def test_rider_performance(ops_client, customer, variant):
    rider_user = User.objects.create_user(phone="+919300000050", name="Rider")
    rider = DeliveryPartner.objects.create(user=rider_user, vehicle_number="UP78AB1234")
    order = _order(customer, "88.00", status=Order.Status.DELIVERED)
    DeliveryAssignment.objects.create(
        order=order, rider=rider, status=DeliveryAssignment.Status.DELIVERED
    )
    OrderReview.objects.create(order=order, user=customer, order_rating=5, rider_rating=4)

    response = ops_client.get(reverse("report-riders"))
    assert response.status_code == 200
    row = response.data[0]
    assert row["rider"] == "+919300000050"
    assert row["delivered"] == 1
    assert row["avg_rider_rating"] == 4.0


# --------------------------------------------------------------------------- #
# Access control & validation
# --------------------------------------------------------------------------- #
def test_customer_cannot_access_reports(customer):
    client = APIClient()
    client.force_authenticate(user=customer)
    assert client.get(reverse("report-sales")).status_code == 403


def test_invalid_date_range_rejected(ops_client):
    response = ops_client.get(reverse("report-sales"), {"start": "not-a-date"})
    assert response.status_code == 400


def test_end_before_start_rejected(ops_client):
    response = ops_client.get(
        reverse("report-sales"), {"start": "2026-06-10", "end": "2026-06-01"}
    )
    assert response.status_code == 400
