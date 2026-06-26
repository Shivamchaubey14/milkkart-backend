from rest_framework import serializers

from .models import phone_validator


class SendOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=17, validators=[phone_validator])


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=17, validators=[phone_validator])
    code = serializers.CharField(max_length=6, min_length=6)


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    phone = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    address = serializers.CharField(read_only=True)
    avatar = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    is_rider = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(read_only=True)

    def get_is_rider(self, obj):
        """True when the user has an active delivery-partner profile."""
        from apps.delivery.models import DeliveryPartner

        try:
            return obj.delivery_partner.is_active
        except DeliveryPartner.DoesNotExist:
            return False


class UserUpdateSerializer(serializers.Serializer):
    """Editable profile fields (phone stays fixed — it's the login identity)."""

    name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    avatar = serializers.CharField(required=False, allow_blank=True)

    def update(self, instance, validated_data):
        changed = [f for f in ("name", "email", "address", "avatar") if f in validated_data]
        for field in changed:
            setattr(instance, field, validated_data[field])
        if changed:
            instance.save(update_fields=changed)
        return instance
