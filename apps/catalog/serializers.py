from rest_framework import serializers

from .models import Category, Product, ProductImage, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "image", "product_count"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "sort_order"]


class ProductVariantSerializer(serializers.ModelSerializer):
    discount_percent = serializers.FloatField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "label",
            "sku",
            "unit",
            "quantity_value",
            "fat_percent",
            "price",
            "mrp",
            "discount_percent",
            "stock",
            "in_stock",
            "is_default",
        ]


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    default_variant = serializers.SerializerMethodField()
    variant_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "brand",
            "category",
            "category_name",
            "default_variant",
            "variant_count",
        ]

    def get_default_variant(self, obj):
        variant = obj.default_variant
        return ProductVariantSerializer(variant).data if variant else None

    def get_variant_count(self, obj):
        return sum(1 for v in obj.variants.all() if v.is_active)


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variants = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "brand",
            "description",
            "tags",
            "category",
            "images",
            "variants",
            "created_at",
        ]

    def get_variants(self, obj):
        active = [v for v in obj.variants.all() if v.is_active]
        return ProductVariantSerializer(active, many=True).data
