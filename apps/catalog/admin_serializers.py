"""Writable catalog serializers for the ops/admin panel (FR-ADM-02).

Unlike the public serializers these expose inactive rows and every editable
field. Catalog cache invalidation is automatic via post_save/post_delete signals.
"""

from rest_framework import serializers

from .models import Category, Product, ProductVariant


class AdminCategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "is_active", "sort_order", "product_count"]
        read_only_fields = ["id", "slug", "product_count"]

    def get_product_count(self, obj):
        return obj.products.count()


class AdminVariantSerializer(serializers.ModelSerializer):
    discount_percent = serializers.FloatField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id", "label", "sku", "unit", "quantity_value", "fat_percent",
            "price", "mrp", "stock", "barcode", "is_default", "is_active",
            "discount_percent", "in_stock",
        ]
        read_only_fields = ["id", "discount_percent", "in_stock"]


class AdminProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    variants = AdminVariantSerializer(many=True, read_only=True)
    variant_count = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "brand", "description", "image_url", "tags",
            "category", "category_name", "is_active",
            "variants", "variant_count", "total_stock", "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at"]

    def get_variant_count(self, obj):
        return obj.variants.count()

    def get_total_stock(self, obj):
        return sum(v.stock for v in obj.variants.all())
