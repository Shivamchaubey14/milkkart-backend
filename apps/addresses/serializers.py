from rest_framework import serializers

from .models import Address


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "address_line",
            "landmark",
            "city",
            "state",
            "pincode",
            "latitude",
            "longitude",
            "is_default",
        ]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
