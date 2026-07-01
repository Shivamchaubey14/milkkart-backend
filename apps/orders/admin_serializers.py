from rest_framework import serializers

from apps.delivery.models import DeliveryAssignment

from .models import Order
from .serializers import OrderItemSerializer


def _rider_brief(obj):
    try:
        assignment = obj.assignment
    except DeliveryAssignment.DoesNotExist:
        return None
    return {
        "rider_id": assignment.rider_id,
        "phone": assignment.rider.user.phone,
        "vehicle_number": assignment.rider.vehicle_number,
        "status": assignment.status,
    }


class AdminOrderSerializer(serializers.ModelSerializer):
    """Order summary for the ops order board, with customer and rider context."""

    customer_phone = serializers.CharField(source="user.phone", read_only=True)
    customer_name = serializers.CharField(source="user.name", read_only=True)
    item_count = serializers.IntegerField(source="items.count", read_only=True)
    rider = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "order_number",
            "status",
            "total",
            "customer_phone",
            "customer_name",
            "address_snapshot",
            "item_count",
            "placed_at",
            "rider",
        ]

    def get_rider(self, obj):
        return _rider_brief(obj)


class AdminOrderDetailSerializer(serializers.ModelSerializer):
    """Full order for the ops detail sheet — items, bill, customer and rider."""

    customer_phone = serializers.CharField(source="user.phone", read_only=True)
    customer_name = serializers.CharField(source="user.name", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    coupon_code = serializers.CharField(source="coupon.code", read_only=True, default=None)
    rider = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    payment_label = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "order_number", "status", "subtotal", "discount", "delivery_fee",
            "small_cart_fee", "tax", "total", "coupon_code", "customer_phone",
            "customer_name", "address_snapshot", "delivery_type", "delivery_date",
            "placed_at", "items", "rider", "payment_method", "payment_label",
        ]

    def get_rider(self, obj):
        return _rider_brief(obj)

    def _payment(self, obj):
        from apps.payments.models import Payment

        try:
            return obj.payment
        except Payment.DoesNotExist:
            return None

    def get_payment_method(self, obj):
        p = self._payment(obj)
        return p.method if p else ""

    def get_payment_label(self, obj):
        p = self._payment(obj)
        return p.get_method_display() if p else ""
