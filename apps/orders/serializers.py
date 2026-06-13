from rest_framework import serializers

from .models import DeliverySlot, Order, OrderItem


class DeliverySlotSerializer(serializers.ModelSerializer):
    available = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)

    class Meta:
        model = DeliverySlot
        fields = ["id", "date", "start_time", "end_time", "capacity", "booked", "available", "is_full"]


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "variant_label", "product_price", "quantity", "subtotal"]


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Order
        fields = ["id", "order_number", "status", "total", "item_count", "placed_at"]


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    delivery_slot = DeliverySlotSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "total",
            "address_snapshot",
            "delivery_slot",
            "notes",
            "items",
            "placed_at",
            "updated_at",
        ]


class CheckoutSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
    delivery_slot_id = serializers.IntegerField(required=False)
    notes = serializers.CharField(required=False, default="", allow_blank=True)
