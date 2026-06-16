from rest_framework import serializers

from apps.delivery.models import DeliveryAssignment

from .models import Order


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
