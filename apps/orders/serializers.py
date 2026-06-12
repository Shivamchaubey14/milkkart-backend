from rest_framework import serializers

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "product_price", "quantity", "subtotal"]


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Order
        fields = ["id", "order_number", "status", "total", "item_count", "placed_at"]


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "total",
            "delivery_address",
            "notes",
            "items",
            "placed_at",
            "updated_at",
        ]


class CheckoutSerializer(serializers.Serializer):
    delivery_address = serializers.CharField()
    notes = serializers.CharField(required=False, default="", allow_blank=True)
