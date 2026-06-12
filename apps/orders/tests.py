from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product
from apps.orders.models import Order

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Test User")


@pytest.fixture
def category(db):
    return Category.objects.create(name="Milk")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Full Cream Milk",
        price=Decimal("28.00"),
        mrp=Decimal("30.00"),
        stock=10,
    )


@pytest.fixture
def product_b(category):
    return Product.objects.create(
        category=category,
        name="Toned Milk",
        price=Decimal("24.00"),
        mrp=Decimal("26.00"),
        stock=5,
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def cart_with_items(user, product, product_b):
    cart = Cart.objects.create(user=user)
    CartItem.objects.create(cart=cart, product=product, quantity=2)
    CartItem.objects.create(cart=cart, product=product_b, quantity=1)
    return cart


@pytest.mark.django_db
class TestOrderModel:
    def test_str(self, user):
        order = Order.objects.create(user=user, total=Decimal("100.00"), delivery_address="123 Main St")
        assert "pending" in str(order)

    def test_default_status(self, user):
        order = Order.objects.create(user=user, total=Decimal("100.00"), delivery_address="123 Main St")
        assert order.status == Order.Status.PENDING


@pytest.mark.django_db
class TestCheckoutAPI:
    def test_checkout_success(self, auth_client, cart_with_items, product, product_b):
        response = auth_client.post(
            reverse("order-checkout"),
            {"delivery_address": "42 Dairy Lane, Mumbai"},
        )
        assert response.status_code == 201
        assert Decimal(response.data["total"]) == Decimal("80.00")
        assert response.data["delivery_address"] == "42 Dairy Lane, Mumbai"
        assert len(response.data["items"]) == 2

        # Stock decremented
        product.refresh_from_db()
        product_b.refresh_from_db()
        assert product.stock == 8
        assert product_b.stock == 4

        # Cart cleared
        assert cart_with_items.items.count() == 0

    def test_checkout_empty_cart(self, auth_client):
        response = auth_client.post(
            reverse("order-checkout"),
            {"delivery_address": "42 Dairy Lane"},
        )
        assert response.status_code == 400
        assert "empty" in response.data["error"].lower()

    def test_checkout_insufficient_stock(self, auth_client, user, product):
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=999)
        response = auth_client.post(
            reverse("order-checkout"),
            {"delivery_address": "42 Dairy Lane"},
        )
        assert response.status_code == 400
        assert "stock" in response.data["error"].lower()

    def test_checkout_missing_address(self, auth_client, cart_with_items):
        response = auth_client.post(reverse("order-checkout"), {})
        assert response.status_code == 400

    def test_checkout_unauthenticated(self):
        client = APIClient()
        response = client.post(reverse("order-checkout"), {"delivery_address": "x"})
        assert response.status_code == 401

    def test_checkout_with_notes(self, auth_client, cart_with_items):
        response = auth_client.post(
            reverse("order-checkout"),
            {"delivery_address": "42 Dairy Lane", "notes": "Ring the bell"},
        )
        assert response.status_code == 201
        assert response.data["notes"] == "Ring the bell"


@pytest.mark.django_db
class TestOrderListAPI:
    def test_list_orders(self, auth_client, cart_with_items):
        auth_client.post(reverse("order-checkout"), {"delivery_address": "Addr 1"})
        response = auth_client.get(reverse("order-list"))
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_list_empty(self, auth_client):
        response = auth_client.get(reverse("order-list"))
        assert response.status_code == 200
        assert len(response.data) == 0

    def test_user_isolation(self, auth_client, cart_with_items):
        auth_client.post(reverse("order-checkout"), {"delivery_address": "Addr 1"})

        other_user = User.objects.create_user(phone="+919876543211", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse("order-list"))
        assert len(response.data) == 0


@pytest.mark.django_db
class TestOrderDetailAPI:
    def test_detail(self, auth_client, cart_with_items):
        checkout_resp = auth_client.post(reverse("order-checkout"), {"delivery_address": "Addr 1"})
        order_number = checkout_resp.data["order_number"]

        response = auth_client.get(reverse("order-detail", kwargs={"order_number": order_number}))
        assert response.status_code == 200
        assert len(response.data["items"]) == 2

    def test_not_found(self, auth_client):
        response = auth_client.get(
            reverse("order-detail", kwargs={"order_number": "00000000-0000-0000-0000-000000000000"})
        )
        assert response.status_code == 404

    def test_other_user_cannot_view(self, auth_client, cart_with_items):
        checkout_resp = auth_client.post(reverse("order-checkout"), {"delivery_address": "Addr 1"})
        order_number = checkout_resp.data["order_number"]

        other_user = User.objects.create_user(phone="+919876543211", name="Other")
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse("order-detail", kwargs={"order_number": order_number}))
        assert response.status_code == 404
