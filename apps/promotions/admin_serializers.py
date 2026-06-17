from rest_framework import serializers

from .models import Banner, Coupon


class AdminCouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "id", "code", "description", "discount_type", "value",
            "min_order_value", "max_discount", "usage_limit", "per_user_limit",
            "first_order_only", "valid_from", "valid_until", "is_active",
            "times_used", "created_at",
        ]
        read_only_fields = ["id", "times_used", "created_at"]


class AdminBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = [
            "id", "title", "subtitle", "image_url", "link_url", "bg_color",
            "is_active", "sort_order", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
