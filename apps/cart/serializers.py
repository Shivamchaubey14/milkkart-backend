from rest_framework import serializers

from apps.catalog.models import ProductVariant

from .billing import compute_bill
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    product_slug = serializers.CharField(source="variant.product.slug", read_only=True)
    image_url = serializers.CharField(source="variant.product.image_url", read_only=True)
    variant_label = serializers.CharField(source="variant.label", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    price = serializers.DecimalField(
        source="variant.price", max_digits=8, decimal_places=2, read_only=True
    )
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "variant",
            "product_name",
            "product_slug",
            "image_url",
            "variant_label",
            "sku",
            "price",
            "quantity",
            "subtotal",
        ]
        read_only_fields = ["variant"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    coupon_code = serializers.SerializerMethodField()
    bill = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "items", "coupon_code", "bill", "item_count"]

    def get_coupon_code(self, obj):
        return obj.applied_coupon.code if obj.applied_coupon else None

    def get_bill(self, obj):
        return compute_bill(obj)


class AddToCartSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_variant_id(self, value):
        try:
            ProductVariant.objects.get(id=value, is_active=True, product__is_active=True)
        except ProductVariant.DoesNotExist:
            raise serializers.ValidationError("Variant not found or inactive.")
        return value


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
