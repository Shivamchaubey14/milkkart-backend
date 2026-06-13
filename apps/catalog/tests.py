from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductImage, ProductVariant


@pytest.fixture
def category(db):
    return Category.objects.create(name="Milk", description="Fresh dairy milk")


@pytest.fixture
def category_inactive(db):
    return Category.objects.create(name="Archived", is_active=False)


@pytest.fixture
def product(db, category):
    p = Product.objects.create(category=category, name="Full Cream Milk", brand="Amul")
    ProductVariant.objects.create(
        product=p, label="500 ml", sku="full-cream-milk-500ml",
        unit=ProductVariant.Unit.ML, quantity_value=500, fat_percent=Decimal("6.0"),
        price=Decimal("28.00"), mrp=Decimal("30.00"), stock=100, is_default=True,
    )
    ProductVariant.objects.create(
        product=p, label="1 L", sku="full-cream-milk-1l",
        unit=ProductVariant.Unit.L, quantity_value=1, fat_percent=Decimal("6.0"),
        price=Decimal("54.00"), mrp=Decimal("58.00"), stock=80,
    )
    return p


@pytest.fixture
def product_out_of_stock(db, category):
    p = Product.objects.create(category=category, name="Toned Milk", brand="Amul")
    ProductVariant.objects.create(
        product=p, label="1 L", sku="toned-milk-1l",
        unit=ProductVariant.Unit.L, quantity_value=1,
        price=Decimal("50.00"), mrp=Decimal("55.00"), stock=0, is_default=True,
    )
    return p


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
        assert str(product) == "Full Cream Milk"

    def test_auto_slug(self, product):
        assert product.slug == "full-cream-milk"

    def test_default_variant_prefers_flagged(self, product):
        assert product.default_variant.sku == "full-cream-milk-500ml"

    def test_default_variant_falls_back_to_cheapest(self, category):
        p = Product.objects.create(category=category, name="No Default")
        ProductVariant.objects.create(
            product=p, label="big", sku="nd-big", price=Decimal("90"), mrp=Decimal("90"), stock=1
        )
        ProductVariant.objects.create(
            product=p, label="small", sku="nd-small", price=Decimal("40"), mrp=Decimal("40"), stock=1
        )
        assert p.default_variant.sku == "nd-small"

    def test_default_variant_none_when_no_active(self, category):
        p = Product.objects.create(category=category, name="Empty")
        assert p.default_variant is None


@pytest.mark.django_db
class TestProductVariantModel:
    def test_str(self, product):
        variant = product.variants.get(sku="full-cream-milk-500ml")
        assert str(variant) == "Full Cream Milk — 500 ml"

    def test_discount_percent(self, product):
        variant = product.variants.get(sku="full-cream-milk-500ml")
        assert float(variant.discount_percent) == 6.7

    def test_discount_percent_zero_mrp(self, category):
        p = Product.objects.create(category=category, name="Free Sample")
        v = ProductVariant.objects.create(
            product=p, label="x", sku="free", price=Decimal("0"), mrp=Decimal("0"), stock=1
        )
        assert v.discount_percent == 0

    def test_in_stock(self, product, product_out_of_stock):
        assert product.variants.get(sku="full-cream-milk-500ml").in_stock is True
        assert product_out_of_stock.variants.first().in_stock is False


@pytest.mark.django_db
class TestProductImageModel:
    def test_str(self, product):
        img = ProductImage.objects.create(product=product, image="test.jpg", sort_order=0)
        assert str(img) == "Full Cream Milk - Image 0"


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

    def test_card_shows_default_variant(self, product):
        response = self.client.get(self.url)
        card = response.data["results"][0]
        assert card["default_variant"]["sku"] == "full-cream-milk-500ml"
        assert Decimal(card["default_variant"]["price"]) == Decimal("28.00")
        assert card["variant_count"] == 2

    def test_filter_by_category(self, product):
        response = self.client.get(self.url, {"category": product.category_id})
        assert len(response.data["results"]) == 1

    def test_filter_by_category_slug(self, product):
        response = self.client.get(self.url, {"category_slug": "milk"})
        assert len(response.data["results"]) == 1

    def test_filter_in_stock(self, product, product_out_of_stock):
        response = self.client.get(self.url, {"in_stock": "true"})
        slugs = [p["slug"] for p in response.data["results"]]
        assert "full-cream-milk" in slugs
        assert "toned-milk" not in slugs

    def test_filter_by_price_range(self, product, product_out_of_stock):
        # Filters on starting price: Toned starts at 50, Full Cream at 28.
        response = self.client.get(self.url, {"min_price": 40, "max_price": 52})
        slugs = [p["slug"] for p in response.data["results"]]
        assert "toned-milk" in slugs
        assert "full-cream-milk" not in slugs

    def test_search(self, product, product_out_of_stock):
        response = self.client.get(self.url, {"search": "Full Cream"})
        assert len(response.data["results"]) == 1

    def test_ordering_by_min_price(self, product, product_out_of_stock):
        response = self.client.get(self.url, {"ordering": "min_price"})
        first = response.data["results"][0]
        assert first["slug"] == "full-cream-milk"  # cheapest variant 28 < 50

    def test_excludes_inactive_products(self, category):
        Product.objects.create(category=category, name="Hidden", is_active=False)
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
        assert response.data["name"] == "Full Cream Milk"
        assert len(response.data["variants"]) == 2
        assert response.data["variants"][0]["discount_percent"] == 6.7
        assert "images" in response.data
        assert "category" in response.data

    def test_detail_not_found(self):
        url = reverse("product-detail", kwargs={"slug": "nonexistent"})
        response = self.client.get(url)
        assert response.status_code == 404
