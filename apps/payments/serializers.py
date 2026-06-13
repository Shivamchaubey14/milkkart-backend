from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    is_paid = serializers.BooleanField(read_only=True)
    order_number = serializers.UUIDField(source="order.order_number", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "payment_id",
            "order_number",
            "method",
            "status",
            "amount",
            "gateway_order_id",
            "is_paid",
            "created_at",
            "updated_at",
        ]


class InitiatePaymentSerializer(serializers.Serializer):
    order_number = serializers.UUIDField()
    method = serializers.ChoiceField(choices=Payment.Method.choices)


class VerifyPaymentSerializer(serializers.Serializer):
    gateway_order_id = serializers.CharField()
    gateway_payment_id = serializers.CharField()
    gateway_signature = serializers.CharField()
