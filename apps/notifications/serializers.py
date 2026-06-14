from rest_framework import serializers

from .models import DeviceToken, Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "category", "title", "body", "data", "is_read", "created_at", "read_at"]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "push_enabled",
            "sms_enabled",
            "email_enabled",
            "order_updates",
            "promotions",
            "subscription_reminders",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class DeviceTokenSerializer(serializers.ModelSerializer):
    # Plain field (no UniqueValidator) — registration upserts on the token.
    token = serializers.CharField(max_length=255)

    class Meta:
        model = DeviceToken
        fields = ["token", "platform", "is_active", "created_at"]
        read_only_fields = ["is_active", "created_at"]
