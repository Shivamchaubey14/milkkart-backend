from rest_framework import serializers

from apps.orders.models import OrderItem

from .models import DeliveryAssignment, DeliveryPartner


class DeliveryPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryPartner
        fields = ["vehicle_number", "is_on_duty", "current_lat", "current_lng", "last_location_at"]


class OrderItemBriefSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "variant_label", "quantity", "subtotal", "is_returned"]


class RiderAssignmentSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(source="order.order_number", read_only=True)
    address = serializers.CharField(source="order.address_snapshot", read_only=True)
    total = serializers.DecimalField(source="order.total", max_digits=10, decimal_places=2, read_only=True)
    items = OrderItemBriefSerializer(source="order.items", many=True, read_only=True)
    is_cod = serializers.SerializerMethodField()
    dest_lat = serializers.SerializerMethodField()
    dest_lng = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryAssignment
        fields = [
            "id",
            "order_number",
            "status",
            "address",
            "total",
            "is_cod",
            "items",
            "dest_lat",
            "dest_lng",
            "assigned_at",
            "accepted_at",
            "picked_up_at",
            "delivered_at",
        ]

    def get_is_cod(self, obj):
        from apps.payments.models import Payment

        try:
            return obj.order.payment.method == Payment.Method.COD
        except Payment.DoesNotExist:
            return False

    def get_dest_lat(self, obj):
        a = getattr(obj.order, "address", None)
        return str(a.latitude) if a and a.latitude is not None else None

    def get_dest_lng(self, obj):
        a = getattr(obj.order, "address", None)
        return str(a.longitude) if a and a.longitude is not None else None


class ReturnSerializer(serializers.Serializer):
    item_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class DutySerializer(serializers.Serializer):
    on_duty = serializers.BooleanField()
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)


class LocationSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6)


class DeliverSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
    proof_photo = serializers.CharField(required=False, allow_blank=True, default="")
    # The rider collected this COD order's amount via the UPI QR (paid to merchant).
    paid_via_upi = serializers.BooleanField(required=False, default=False)
