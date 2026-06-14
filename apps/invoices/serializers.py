from rest_framework import serializers

from .models import Invoice


class InvoiceSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(source="order.order_number", read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)
    address_snapshot = serializers.CharField(source="order.address_snapshot", read_only=True)
    placed_at = serializers.DateTimeField(source="order.placed_at", read_only=True)
    items = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "order_number",
            "order_status",
            "subtotal",
            "discount",
            "delivery_fee",
            "small_cart_fee",
            "tax",
            "total",
            "address_snapshot",
            "items",
            "placed_at",
            "issued_at",
            "emailed_at",
        ]

    def get_items(self, obj):
        from apps.orders.serializers import OrderItemSerializer

        return OrderItemSerializer(obj.order.items.all(), many=True).data
