from rest_framework import serializers

from .models import StockMovement


class StockMovementSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    order_number = serializers.UUIDField(source="order.order_number", read_only=True, default=None)
    created_by_phone = serializers.CharField(source="created_by.phone", read_only=True, default=None)

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "variant",
            "sku",
            "product_name",
            "delta",
            "reason",
            "balance_after",
            "note",
            "order_number",
            "created_by_phone",
            "created_at",
        ]


class RestockSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AdjustStockSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    delta = serializers.IntegerField()
    reason = serializers.ChoiceField(
        choices=[
            StockMovement.Reason.ADJUSTMENT,
            StockMovement.Reason.DAMAGE,
        ]
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("delta must be non-zero.")
        return value


class LowStockSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(source="id")
    sku = serializers.CharField()
    product_name = serializers.CharField(source="product.name")
    label = serializers.CharField()
    stock = serializers.IntegerField()
