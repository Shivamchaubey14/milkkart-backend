from rest_framework import serializers

from .models import FAQ, OrderReview, ProductRating, SupportTicket, TicketMessage


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ["id", "topic", "question", "answer", "sort_order"]


class OrderReviewSerializer(serializers.ModelSerializer):
    order_rating = serializers.IntegerField(min_value=1, max_value=5)
    rider_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)

    class Meta:
        model = OrderReview
        fields = ["id", "order_rating", "rider_rating", "comment", "photos", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProductRatingSerializer(serializers.ModelSerializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    user_name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = ProductRating
        fields = ["id", "rating", "comment", "photos", "user_name", "created_at"]
        read_only_fields = ["id", "user_name", "created_at"]


class ProductRatingCreateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    photos = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    order_number = serializers.UUIDField(required=False, allow_null=True)


class TicketMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketMessage
        fields = ["id", "is_staff", "body", "created_at"]
        read_only_fields = fields


class SupportTicketSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(source="order.order_number", read_only=True, default=None)
    messages = TicketMessageSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "ticket_number",
            "order_number",
            "reason",
            "subject",
            "description",
            "photos",
            "status",
            "resolution_type",
            "resolution_note",
            "refund_amount",
            "messages",
            "created_at",
            "updated_at",
            "resolved_at",
        ]
        read_only_fields = [
            "id",
            "ticket_number",
            "status",
            "resolution_type",
            "resolution_note",
            "refund_amount",
            "created_at",
            "updated_at",
            "resolved_at",
        ]


class SupportTicketCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=SupportTicket.Reason.choices)
    subject = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    photos = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    order_number = serializers.UUIDField(required=False, allow_null=True)


class TicketMessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField()


class ResolveTicketSerializer(serializers.Serializer):
    resolution_type = serializers.ChoiceField(
        choices=[
            SupportTicket.Resolution.REPLACEMENT,
            SupportTicket.Resolution.REFUND,
        ]
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
