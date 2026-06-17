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
    # Surfaced so the web/app can offer one-tap reorder (FR-ORD-04). The variant
    # may have been deleted (SET_NULL) or be out of stock, so both are nullable.
    variant_id = serializers.SerializerMethodField()
    variant_in_stock = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product_name",
            "variant_label",
            "product_price",
            "quantity",
            "subtotal",
            "variant_id",
            "variant_in_stock",
        ]

    def get_variant_id(self, obj):
        return obj.variant_id

    def get_variant_in_stock(self, obj):
        return bool(obj.variant and obj.variant.stock >= obj.quantity)


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Order
        fields = ["id", "order_number", "status", "total", "item_count", "placed_at"]


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    delivery_slot = DeliverySlotSerializer(read_only=True)
    coupon_code = serializers.CharField(source="coupon.code", read_only=True, default=None)
    assignment = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "subtotal",
            "discount",
            "delivery_fee",
            "small_cart_fee",
            "tax",
            "total",
            "coupon_code",
            "address_snapshot",
            "destination",
            "delivery_slot",
            "notes",
            "items",
            "assignment",
            "placed_at",
            "updated_at",
        ]

    def get_destination(self, obj):
        """Delivery address coordinates for live-tracking the rider, when known."""
        addr = getattr(obj, "address", None)
        if addr and addr.latitude is not None and addr.longitude is not None:
            return {"lat": str(addr.latitude), "lng": str(addr.longitude)}
        return None

    def get_assignment(self, obj):
        from apps.delivery.models import DeliveryAssignment

        try:
            assignment = obj.assignment
        except DeliveryAssignment.DoesNotExist:
            return None
        rider = assignment.rider
        return {
            "status": assignment.status,
            "rider_phone": rider.user.phone,
            "vehicle_number": rider.vehicle_number,
            "delivery_otp": assignment.delivery_otp,  # shown to the rider on delivery
            "rider_lat": str(rider.current_lat) if rider.current_lat is not None else None,
            "rider_lng": str(rider.current_lng) if rider.current_lng is not None else None,
        }


class CheckoutSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
    delivery_slot_id = serializers.IntegerField(required=False)
    notes = serializers.CharField(required=False, default="", allow_blank=True)
