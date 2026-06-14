from rest_framework import serializers

from .models import DeliveryAssignment, DeliveryPartner


class DeliveryPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryPartner
        fields = ["vehicle_number", "is_on_duty", "current_lat", "current_lng", "last_location_at"]


class RiderAssignmentSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(source="order.order_number", read_only=True)
    address = serializers.CharField(source="order.address_snapshot", read_only=True)
    total = serializers.DecimalField(source="order.total", max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = DeliveryAssignment
        fields = [
            "id",
            "order_number",
            "status",
            "address",
            "total",
            "assigned_at",
            "accepted_at",
            "picked_up_at",
            "delivered_at",
        ]


class DutySerializer(serializers.Serializer):
    on_duty = serializers.BooleanField()
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)


class LocationSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6)


class DeliverSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
    proof_photo = serializers.CharField(required=False, allow_blank=True, default="")
