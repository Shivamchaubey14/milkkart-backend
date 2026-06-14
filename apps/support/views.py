from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Product, ProductVariant
from apps.core.permissions import IsSupportAgent
from apps.orders.models import Order

from . import services
from .models import FAQ, OrderReview, ProductRating, SupportTicket, TicketMessage
from .serializers import (
    FAQSerializer,
    OrderReviewSerializer,
    ProductRatingCreateSerializer,
    ProductRatingSerializer,
    ResolveTicketSerializer,
    SupportTicketCreateSerializer,
    SupportTicketSerializer,
    TicketMessageCreateSerializer,
)


# --------------------------------------------------------------------------- #
# Help centre
# --------------------------------------------------------------------------- #
class FAQListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FAQSerializer
    queryset = FAQ.objects.filter(is_active=True)


# --------------------------------------------------------------------------- #
# Ratings & reviews
# --------------------------------------------------------------------------- #
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def order_rating(request, order_number):
    """Retrieve or submit the post-delivery rating for one of the user's orders."""
    try:
        order = Order.objects.get(order_number=order_number, user=request.user)
    except Order.DoesNotExist:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        review = OrderReview.objects.filter(order=order).first()
        if not review:
            return Response({"error": "This order has not been rated yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrderReviewSerializer(review).data)

    if order.status != Order.Status.DELIVERED:
        return Response(
            {"error": "You can only rate an order once it has been delivered."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = OrderReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    review, _ = OrderReview.objects.update_or_create(
        order=order,
        defaults={"user": request.user, **serializer.validated_data},
    )
    return Response(OrderReviewSerializer(review).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def product_rating(request, product_id):
    """List a product's ratings, or submit/update the user's own rating for it."""
    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return Response({"error": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        ratings = ProductRating.objects.filter(product=product).select_related("user")
        return Response(
            {
                "average": product.rating_average,
                "count": product.rating_count,
                "ratings": ProductRatingSerializer(ratings, many=True).data,
            }
        )

    serializer = ProductRatingCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    variant = None
    if data.get("variant_id"):
        variant = ProductVariant.objects.filter(pk=data["variant_id"], product=product).first()
        if not variant:
            return Response(
                {"error": "Variant does not belong to this product."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    order = None
    if data.get("order_number"):
        order = Order.objects.filter(order_number=data["order_number"], user=request.user).first()
        if not order:
            return Response({"error": "Order not found."}, status=status.HTTP_400_BAD_REQUEST)

    rating = services.record_product_rating(
        request.user,
        product,
        data["rating"],
        variant=variant,
        order=order,
        comment=data.get("comment", ""),
        photos=data.get("photos", []),
    )
    return Response(ProductRatingSerializer(rating).data, status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------- #
# Support tickets
# --------------------------------------------------------------------------- #
class SupportTicketListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportTicketSerializer

    def get_queryset(self):
        return (
            SupportTicket.objects.filter(user=self.request.user)
            .select_related("order")
            .prefetch_related("messages")
        )

    def create(self, request, *args, **kwargs):
        serializer = SupportTicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = None
        if data.get("order_number"):
            order = Order.objects.filter(
                order_number=data["order_number"], user=request.user
            ).first()
            if not order:
                return Response({"error": "Order not found."}, status=status.HTTP_400_BAD_REQUEST)

        ticket = SupportTicket.objects.create(
            user=request.user,
            order=order,
            reason=data["reason"],
            subject=data["subject"],
            description=data.get("description", ""),
            photos=data.get("photos", []),
        )
        return Response(SupportTicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


def _get_ticket(request, ticket_number, *, staff=False):
    qs = SupportTicket.objects.select_related("order").prefetch_related("messages")
    if not staff:
        qs = qs.filter(user=request.user)
    return qs.get(ticket_number=ticket_number)


class SupportTicketDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportTicketSerializer
    lookup_field = "ticket_number"

    def get_queryset(self):
        return (
            SupportTicket.objects.filter(user=self.request.user)
            .select_related("order")
            .prefetch_related("messages")
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_ticket_message(request, ticket_number):
    """Append a message to a ticket thread (customer side)."""
    try:
        ticket = _get_ticket(request, ticket_number)
    except SupportTicket.DoesNotExist:
        return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = TicketMessageCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    TicketMessage.objects.create(
        ticket=ticket,
        author=request.user,
        is_staff=False,
        body=serializer.validated_data["body"],
    )
    return Response(SupportTicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsSupportAgent])
def resolve_ticket(request, ticket_number):
    """Agent resolves a ticket via replacement or wallet refund."""
    try:
        ticket = _get_ticket(request, ticket_number, staff=True)
    except SupportTicket.DoesNotExist:
        return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = ResolveTicketSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        services.resolve_ticket(
            ticket,
            resolution_type=data["resolution_type"],
            note=data.get("note", ""),
            amount=data.get("amount"),
        )
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(SupportTicketSerializer(ticket).data)
