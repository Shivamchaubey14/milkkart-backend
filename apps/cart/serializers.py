from rest_framework import serializers

from apps.catalog.models import ProductVariant

from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    product_slug = serializers.CharField(source="variant.product.slug", read_only=True)
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
            "variant_label",
            "sku",
            "price",
            "quantity",
            "subtotal",
        ]
        read_only_fields = ["variant"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "items", "total", "item_count"]


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
