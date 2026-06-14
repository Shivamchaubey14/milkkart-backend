from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import Order, OrderItem

from .models import Invoice
from .services import build_statement, generate_invoice

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876500001", name="Inv User", email="inv@example.com")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def variant(db):
    category = Category.objects.create(name="Milk")
    product = Product.objects.create(category=category, name="Full Cream Milk")
    return ProductVariant.objects.create(
        product=product, label="500 ml", sku="MILK-500", price=Decimal("30.00"), mrp=Decimal("32.00"), stock=50
    )


@pytest.fixture
def order(user, variant):
    order = Order.objects.create(
        user=user,
        status=Order.Status.DELIVERED,
        subtotal=Decimal("60.00"),
        discount=Decimal("0.00"),
        delivery_fee=Decimal("25.00"),
        small_cart_fee=Decimal("0.00"),
        tax=Decimal("3.00"),
        total=Decimal("88.00"),
        address_snapshot="12 Dairy Lane, Pune",
    )
    OrderItem.objects.create(
        order=order,
        variant=variant,
        product_name=variant.product.name,
        variant_label=variant.label,
        product_price=variant.price,
        quantity=2,
    )
    return order


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
def test_generate_invoice_snapshots_totals_and_numbers(order):
    invoice = generate_invoice(order)
    assert invoice.number.startswith(f"INV-{invoice.issued_at:%Y}-")
    assert invoice.total == order.total
    assert invoice.subtotal == order.subtotal
    assert invoice.tax == order.tax


def test_generate_invoice_is_idempotent(order):
    first = generate_invoice(order)
    second = generate_invoice(order)
    assert first.pk == second.pk
    assert Invoice.objects.filter(order=order).count() == 1


def test_build_statement_aggregates(order, user):
    generate_invoice(order)
    year, month = order.placed_at.year, order.placed_at.month
    statement = build_statement(user, year, month)
    assert statement["invoice_count"] == 1
    assert statement["total_billed"] == "88.00"
    assert statement["subscription_summary"] is not None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_invoice_for_order_generates_and_returns(auth_client, order):
    url = reverse("invoice-for-order", args=[order.order_number])
    response = auth_client.get(url)
    assert response.status_code == 200
    assert response.data["total"] == "88.00"
    assert len(response.data["items"]) == 1
    assert Invoice.objects.filter(order=order).exists()


def test_email_invoice_stamps_emailed_at(auth_client, order):
    url = reverse("invoice-email", args=[order.order_number])
    response = auth_client.post(url)
    assert response.status_code == 200
    assert response.data["emailed_at"] is not None


def test_invoice_for_other_users_order_is_404(auth_client, variant):
    other = User.objects.create_user(phone="+919876500002", name="Other")
    others_order = Order.objects.create(user=other, total=Decimal("10.00"))
    url = reverse("invoice-for-order", args=[others_order.order_number])
    assert auth_client.get(url).status_code == 404


def test_statement_endpoint_lists_invoices(auth_client, order):
    generate_invoice(order)
    url = reverse("invoice-statement")
    response = auth_client.get(url, {"month": f"{order.placed_at:%Y-%m}"})
    assert response.status_code == 200
    assert response.data["invoice_count"] == 1
    assert len(response.data["invoices"]) == 1


def test_statement_rejects_bad_month(auth_client):
    response = auth_client.get(reverse("invoice-statement"), {"month": "nope"})
    assert response.status_code == 400


def test_invoice_list_is_scoped_to_user(auth_client, order):
    generate_invoice(order)
    other = User.objects.create_user(phone="+919876500003", name="Other")
    others_order = Order.objects.create(user=other, total=Decimal("5.00"))
    generate_invoice(others_order)
    response = auth_client.get(reverse("invoice-list"))
    assert response.status_code == 200
    assert response.data["count"] == 1
