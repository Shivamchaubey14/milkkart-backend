from rest_framework import serializers

from .models import Wallet, WalletTransaction


class WalletTransactionSerializer(serializers.ModelSerializer):
    signed_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    order_number = serializers.UUIDField(source="order.order_number", read_only=True, default=None)

    class Meta:
        model = WalletTransaction
        fields = [
            "id",
            "type",
            "amount",
            "signed_amount",
            "balance_after",
            "order_number",
            "description",
            "created_at",
        ]


class WalletSerializer(serializers.ModelSerializer):
    recent_transactions = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ["balance", "recent_transactions"]

    def get_recent_transactions(self, obj):
        recent = obj.transactions.all()[:5]
        return WalletTransactionSerializer(recent, many=True).data


class TopupSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1, max_value=100000)


class TopupVerifySerializer(serializers.Serializer):
    gateway_order_id = serializers.CharField()
    gateway_payment_id = serializers.CharField()
    gateway_signature = serializers.CharField()
