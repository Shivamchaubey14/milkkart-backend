from rest_framework import serializers

from .models import ServiceableArea


class ServiceableAreaSerializer(serializers.ModelSerializer):
    has_geofence = serializers.BooleanField(read_only=True)

    class Meta:
        model = ServiceableArea
        fields = [
            "id",
            "pincode",
            "area_name",
            "city",
            "is_active",
            "delivery_eta_minutes",
            "center_lat",
            "center_lng",
            "radius_km",
            "has_geofence",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
