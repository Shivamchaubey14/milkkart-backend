from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductImage


@pytest.fixture
def category(db):
    return Category.objects.create(name="Milk", description="Fresh dairy milk")


@pytest.fixture
def category_inactive(db):
    return Category.objects.create(name="Archived", is_active=False)


@pytest.fixture
def product(db, category):
    return Product.objects.create(
        category=category,
        name="Full Cream Milk 500ml",
        price=Decimal("28.00"),
        mrp=Decimal("30.00"),
        unit=Product.Unit.ML,
        quantity_value=500,
        stock=100,
    )


@pytest.fixture
def product_out_of_stock(db, category):
    return Product.objects.create(
        category=category,
        name="Toned Milk 1L",
        price=Decimal("50.00"),
        mrp=Decimal("55.00"),
        unit=Product.Unit.L,
        quantity_value=1,
        stock=0,
    )


@pytest.mark.django_db
class TestCategoryModel:
    def test_str(self, category):
        assert str(category) == "Milk"

    def test_auto_slug(self, category):
        assert category.slug == "milk"

    def test_ordering(self, db):
        Category.objects.create(name="Curd", sort_order=2)
        Category.objects.create(name="Butter", sort_order=1)
        categories = list(Category.objects.values_list("name", flat=True))
        assert categories.index("Butter") < categories.index("Curd")


@pytest.mark.django_db
class TestProductModel:
    def test_str(self, product):
        assert str(product) == "Full Cream Milk 500ml"

    def test_auto_slug(self, product):
        assert product.slug == "full-cream-milk-500ml"

    def test_discount_percent(self, product):
        assert float(product.discount_percent) == 6.7

    def test_discount_percent_zero_mrp(self, category):
        p = Product.objects.create(
            category=category, name="Free Sample", price=Decimal("0"), mrp=Decimal("0"), stock=1
        )
        assert p.discount_percent == 0

    def test_in_stock_true(self, product):
        assert product.in_stock is True

    def test_in_stock_false(self, product_out_of_stock):
        assert product_out_of_stock.in_stock is False


@pytest.mark.django_db
class TestProductImageModel:
    def test_str(self, product):
        img = ProductImage.objects.create(product=product, image="test.jpg", sort_order=0)
        assert str(img) == "Full Cream Milk 500ml - Image 0"


@pytest.mark.django_db
class TestCategoryListAPI:
    def setup_method(self):
        self.client = APIClient()
        self.url = reverse("category-list")

    def test_list_categories(self, category):
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["name"] == "Milk"

    def test_excludes_inactive(self, category, category_inactive):
        response = self.client.get(self.url)
        names = [c["name"] for c in response.data["results"]]
        assert "Milk" in names
        assert "Archived" not in names

    def test_includes_product_count(self, product):
        response = self.client.get(self.url)
        assert response.data["results"][0]["product_count"] == 1


@pytest.mark.django_db
class TestProductListAPI:
    def setup_method(self):
        self.client = APIClient()
        self.url = reverse("product-list")

    def test_list_products(self, product):
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_by_category(self, product):
        response = self.client.get(self.url, {"category": product.category_id})
        assert len(response.data["results"]) == 1

    def test_filter_by_category_slug(self, product):
        response = self.client.get(self.url, {"category_slug": "milk"})
        assert len(response.data["results"]) == 1

    def test_filter_in_stock(self, product, product_out_of_stock):
        response = self.client.get(self.url, {"in_stock": "true"})
        slugs = [p["slug"] for p in response.data["results"]]
        assert "full-cream-milk-500ml" in slugs
        assert "toned-milk-1l" not in slugs

    def test_filter_by_price_range(self, product, product_out_of_stock):
        response = self.client.get(self.url, {"min_price": 40, "max_price": 60})
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["slug"] == "toned-milk-1l"

    def test_search(self, product, product_out_of_stock):
        response = self.client.get(self.url, {"search": "Full Cream"})
        assert len(response.data["results"]) == 1

    def test_ordering_by_price(self, product, product_out_of_stock):
        response = self.client.get(self.url, {"ordering": "price"})
        prices = [r["price"] for r in response.data["results"]]
        assert prices == sorted(prices)

    def test_excludes_inactive_products(self, category):
        Product.objects.create(
            category=category, name="Hidden", price=Decimal("10"), mrp=Decimal("10"), is_active=False
        )
        response = self.client.get(self.url)
        assert len(response.data["results"]) == 0


@pytest.mark.django_db
class TestProductDetailAPI:
    def setup_method(self):
        self.client = APIClient()

    def test_detail_by_slug(self, product):
        url = reverse("product-detail", kwargs={"slug": product.slug})
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["name"] == "Full Cream Milk 500ml"
        assert response.data["discount_percent"] == 6.7
        assert response.data["in_stock"] is True
        assert "images" in response.data
        assert "category" in response.data

    def test_detail_not_found(self):
        url = reverse("product-detail", kwargs={"slug": "nonexistent"})
        response = self.client.get(url)
        assert response.status_code == 404
