from rest_framework import serializers

from .models import StoreConfig


class StoreConfigSerializer(serializers.ModelSerializer):
    """Read/write the single storefront config row from the admin console."""

    class Meta:
        model = StoreConfig
        fields = [
            "free_delivery_threshold",
            "delivery_fee",
            "small_cart_threshold",
            "small_cart_fee",
            "tax_percent",
            "next_day_enabled",
            "next_day_window_start",
            "next_day_window_end",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]
