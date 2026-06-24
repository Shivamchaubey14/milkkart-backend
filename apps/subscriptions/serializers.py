import datetime

from rest_framework import serializers

from apps.addresses.models import Address
from apps.catalog.models import ProductVariant

from .models import Subscription, SubscriptionDelivery, SubscriptionVacation


class SubscriptionVacationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionVacation
        fields = ["id", "start_date", "end_date"]

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError("end_date must not be before start_date.")
        return attrs


class SubscriptionDeliverySerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(source="order.order_number", read_only=True, default=None)

    class Meta:
        model = SubscriptionDelivery
        fields = ["id", "date", "quantity", "amount", "status", "order_number"]


class SubscriptionSerializer(serializers.ModelSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        source="variant", queryset=ProductVariant.objects.filter(is_active=True)
    )
    address_id = serializers.PrimaryKeyRelatedField(source="address", queryset=Address.objects.all())
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    image_url = serializers.CharField(source="variant.product.image_url", read_only=True)
    variant_label = serializers.CharField(source="variant.label", read_only=True)
    daily_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    vacations = SubscriptionVacationSerializer(many=True, read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "variant_id",
            "product_name",
            "image_url",
            "variant_label",
            "quantity",
            "frequency",
            "custom_days",
            "address_id",
            "preferred_time",
            "status",
            "start_date",
            "daily_cost",
            "vacations",
            "created_at",
        ]
        read_only_fields = ["status", "created_at"]

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

    def validate_address_id(self, address):
        request = self.context.get("request")
        if request and address.user_id != request.user.id:
            raise serializers.ValidationError("Address not found.")
        from apps.serviceability.services import is_serviceable

        if not is_serviceable(address):
            raise serializers.ValidationError("We don't deliver to this address yet.")
        return address

    def validate(self, attrs):
        frequency = attrs.get("frequency", getattr(self.instance, "frequency", None))
        custom_days = attrs.get("custom_days", getattr(self.instance, "custom_days", []))
        if frequency == Subscription.Frequency.CUSTOM:
            if not custom_days:
                raise serializers.ValidationError(
                    {"custom_days": "Provide at least one date for a custom calendar."}
                )
            for value in custom_days:
                try:
                    datetime.date.fromisoformat(value)
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        {"custom_days": f"'{value}' is not a valid ISO date (YYYY-MM-DD)."}
                    )
        elif "custom_days" in attrs:
            attrs["custom_days"] = []
        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class SkipSerializer(serializers.Serializer):
    date = serializers.DateField()


class SetQuantitySerializer(serializers.Serializer):
    date = serializers.DateField()
    quantity = serializers.IntegerField(min_value=1)
