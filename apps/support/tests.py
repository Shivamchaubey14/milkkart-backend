from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import Order
from apps.wallet.models import WalletTransaction, get_or_create_wallet

from . import services
from .models import FAQ, OrderReview, ProductRating, SupportTicket, TicketMessage

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876600001", name="Sup User")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def staff(db):
    return User.objects.create_superuser(phone="+919876600099", name="Agent")


@pytest.fixture
def staff_client(staff):
    client = APIClient()
    client.force_authenticate(user=staff)
    return client


@pytest.fixture
def product(db):
    category = Category.objects.create(name="Milk")
    return Product.objects.create(category=category, name="Full Cream Milk")


@pytest.fixture
def variant(product):
    return ProductVariant.objects.create(
        product=product, label="500 ml", sku="MILK-500", price=Decimal("30.00"), mrp=Decimal("32.00"), stock=50
    )


@pytest.fixture
def delivered_order(user):
    return Order.objects.create(
        user=user, status=Order.Status.DELIVERED, total=Decimal("88.00")
    )


# --------------------------------------------------------------------------- #
# FAQs
# --------------------------------------------------------------------------- #
def test_faq_list_returns_only_active(auth_client):
    FAQ.objects.create(question="How do I pay?", answer="Wallet or card.", is_active=True)
    FAQ.objects.create(question="Hidden?", answer="No.", is_active=False)
    response = auth_client.get(reverse("faq-list"))
    assert response.status_code == 200
    assert response.data["count"] == 1


# --------------------------------------------------------------------------- #
# Order reviews
# --------------------------------------------------------------------------- #
def test_rate_order_requires_delivery(auth_client, user):
    order = Order.objects.create(user=user, status=Order.Status.CONFIRMED, total=Decimal("10.00"))
    url = reverse("order-rating", args=[order.order_number])
    response = auth_client.post(url, {"order_rating": 5}, format="json")
    assert response.status_code == 400


def test_rate_delivered_order(auth_client, delivered_order):
    url = reverse("order-rating", args=[delivered_order.order_number])
    response = auth_client.post(
        url, {"order_rating": 5, "rider_rating": 4, "comment": "Great"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["order_rating"] == 5
    assert OrderReview.objects.filter(order=delivered_order).count() == 1


def test_rerating_order_updates_same_review(auth_client, delivered_order):
    url = reverse("order-rating", args=[delivered_order.order_number])
    auth_client.post(url, {"order_rating": 3}, format="json")
    auth_client.post(url, {"order_rating": 5}, format="json")
    assert OrderReview.objects.filter(order=delivered_order).count() == 1
    assert OrderReview.objects.get(order=delivered_order).order_rating == 5


def test_get_order_rating_before_submission_is_404(auth_client, delivered_order):
    url = reverse("order-rating", args=[delivered_order.order_number])
    assert auth_client.get(url).status_code == 404


def test_rating_out_of_range_rejected(auth_client, delivered_order):
    url = reverse("order-rating", args=[delivered_order.order_number])
    response = auth_client.post(url, {"order_rating": 6}, format="json")
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Product ratings & aggregation
# --------------------------------------------------------------------------- #
def test_product_rating_updates_aggregate(auth_client, product, variant):
    other = User.objects.create_user(phone="+919876600002", name="Two")
    services.record_product_rating(other, product, 4)
    url = reverse("product-rating", args=[product.id])
    response = auth_client.post(url, {"rating": 2, "variant_id": variant.id}, format="json")
    assert response.status_code == 201

    product.refresh_from_db()
    assert product.rating_count == 2
    assert product.rating_average == 3.0


def test_product_rating_surfaces_on_catalog(auth_client, user, product):
    services.record_product_rating(user, product, 5)
    response = auth_client.get(reverse("product-detail", args=[product.slug]))
    assert response.status_code == 200
    assert response.data["rating_count"] == 1
    assert response.data["rating_average"] == 5.0


def test_re_rating_product_same_order_keeps_one_row(auth_client, user, product):
    services.record_product_rating(user, product, 3)
    services.record_product_rating(user, product, 5)
    assert ProductRating.objects.filter(user=user, product=product).count() == 1
    product.refresh_from_db()
    assert product.rating_count == 1
    assert product.rating_average == 5.0


# --------------------------------------------------------------------------- #
# Support tickets
# --------------------------------------------------------------------------- #
def test_create_ticket_with_order(auth_client, delivered_order):
    response = auth_client.post(
        reverse("ticket-list"),
        {
            "reason": "damaged_item",
            "subject": "Spilled milk",
            "description": "Carton was torn.",
            "order_number": str(delivered_order.order_number),
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == "open"
    assert response.data["order_number"] == str(delivered_order.order_number)


def test_create_ticket_with_foreign_order_rejected(auth_client):
    other = User.objects.create_user(phone="+919876600003", name="Three")
    others_order = Order.objects.create(user=other, total=Decimal("10.00"))
    response = auth_client.post(
        reverse("ticket-list"),
        {"reason": "wrong_item", "subject": "x", "order_number": str(others_order.order_number)},
        format="json",
    )
    assert response.status_code == 400


def test_ticket_list_is_scoped(auth_client, user):
    SupportTicket.objects.create(user=user, reason="other", subject="Mine")
    other = User.objects.create_user(phone="+919876600004", name="Four")
    SupportTicket.objects.create(user=other, reason="other", subject="Theirs")
    response = auth_client.get(reverse("ticket-list"))
    assert response.data["count"] == 1


def test_add_message_to_ticket(auth_client, user):
    ticket = SupportTicket.objects.create(user=user, reason="other", subject="Help")
    url = reverse("ticket-message", args=[ticket.ticket_number])
    response = auth_client.post(url, {"body": "Any update?"}, format="json")
    assert response.status_code == 201
    assert TicketMessage.objects.filter(ticket=ticket, is_staff=False).count() == 1


# --------------------------------------------------------------------------- #
# Ticket resolution
# --------------------------------------------------------------------------- #
def test_resolve_with_refund_credits_wallet(user, delivered_order):
    ticket = SupportTicket.objects.create(
        user=user, order=delivered_order, reason="damaged_item", subject="Bad"
    )
    services.resolve_ticket(
        ticket, resolution_type=SupportTicket.Resolution.REFUND, amount=Decimal("50.00")
    )
    ticket.refresh_from_db()
    assert ticket.status == SupportTicket.Status.RESOLVED
    assert ticket.refund_amount == Decimal("50.00")
    wallet = get_or_create_wallet(user)
    assert wallet.balance == Decimal("50.00")
    assert wallet.transactions.filter(type=WalletTransaction.Type.REFUND).exists()


def test_resolve_with_replacement(user):
    ticket = SupportTicket.objects.create(user=user, reason="wrong_item", subject="x")
    services.resolve_ticket(
        ticket, resolution_type=SupportTicket.Resolution.REPLACEMENT, note="Re-sent"
    )
    ticket.refresh_from_db()
    assert ticket.status == SupportTicket.Status.RESOLVED
    assert ticket.resolution_type == SupportTicket.Resolution.REPLACEMENT
    assert ticket.refund_amount is None


def test_refund_without_amount_raises(user):
    ticket = SupportTicket.objects.create(user=user, reason="other", subject="x")
    with pytest.raises(ValueError):
        services.resolve_ticket(ticket, resolution_type=SupportTicket.Resolution.REFUND)


def test_resolve_endpoint_requires_staff(auth_client, user):
    ticket = SupportTicket.objects.create(user=user, reason="other", subject="x")
    url = reverse("ticket-resolve", args=[ticket.ticket_number])
    response = auth_client.post(url, {"resolution_type": "replacement"}, format="json")
    assert response.status_code == 403


def test_staff_can_resolve_ticket(staff_client, user):
    ticket = SupportTicket.objects.create(user=user, reason="other", subject="x")
    url = reverse("ticket-resolve", args=[ticket.ticket_number])
    response = staff_client.post(url, {"resolution_type": "replacement"}, format="json")
    assert response.status_code == 200
    assert response.data["status"] == "resolved"
