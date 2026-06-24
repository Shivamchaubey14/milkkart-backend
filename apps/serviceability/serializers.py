from rest_framework import serializers

from .models import DeliveryZone, ServiceableArea


class DeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = [
            "id",
            "name",
            "city",
            "state",
            "polygon",
            "is_active",
            "delivery_eta_minutes",
            "priority",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_polygon(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("polygon must be a GeoJSON geometry object.")
        geom_type = value.get("type")
        coords = value.get("coordinates")
        if geom_type not in ("Polygon", "MultiPolygon"):
            raise serializers.ValidationError("polygon.type must be 'Polygon' or 'MultiPolygon'.")
        if not isinstance(coords, list) or not coords:
            raise serializers.ValidationError("polygon.coordinates must be a non-empty list.")
        # Each (Multi)Polygon's outer ring needs at least 3 distinct points (a closed ring is 4).
        rings = coords if geom_type == "Polygon" else [poly[0] for poly in coords if poly]
        for ring in rings:
            if not isinstance(ring, list) or len(ring) < 4:
                raise serializers.ValidationError("Each polygon ring needs at least 4 points (closed).")
        return value


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
