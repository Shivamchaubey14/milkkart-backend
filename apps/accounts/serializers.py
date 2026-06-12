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
    date_joined = serializers.DateTimeField(read_only=True)
