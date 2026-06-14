import datetime

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Subscription, SubscriptionDelivery, SubscriptionVacation
from .serializers import (
    SetQuantitySerializer,
    SkipSerializer,
    SubscriptionSerializer,
    SubscriptionVacationSerializer,
)


def _get_subscription(request, pk):
    return Subscription.objects.filter(user=request.user).select_related(
        "variant__product", "address"
    ).get(pk=pk)


class SubscriptionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        return (
            Subscription.objects.filter(user=self.request.user)
            .select_related("variant__product", "address")
            .prefetch_related("vacations")
        )


class SubscriptionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        return (
            Subscription.objects.filter(user=self.request.user)
            .select_related("variant__product", "address")
            .prefetch_related("vacations")
        )

    def perform_destroy(self, instance):
        """Cancelling is soft — keep history, stop future generation."""
        instance.status = Subscription.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pause(request, pk):
    try:
        subscription = _get_subscription(request, pk)
    except Subscription.DoesNotExist:
        return Response({"error": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)
    if subscription.status == Subscription.Status.CANCELLED:
        return Response(
            {"error": "A cancelled subscription cannot be paused."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    subscription.status = Subscription.Status.PAUSED
    subscription.save(update_fields=["status", "updated_at"])
    return Response(SubscriptionSerializer(subscription, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resume(request, pk):
    try:
        subscription = _get_subscription(request, pk)
    except Subscription.DoesNotExist:
        return Response({"error": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)
    if subscription.status == Subscription.Status.CANCELLED:
        return Response(
            {"error": "A cancelled subscription cannot be resumed."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=["status", "updated_at"])
    return Response(SubscriptionSerializer(subscription, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def skip(request, pk):
    try:
        subscription = _get_subscription(request, pk)
    except Subscription.DoesNotExist:
        return Response({"error": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = SkipSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    date = serializer.validated_data["date"]

    if not services.is_change_allowed(date):
        return Response(
            {"error": "The 10 PM cutoff for this delivery date has passed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing = subscription.deliveries.filter(date=date).first()
    if existing and existing.is_generated:
        return Response(
            {"error": "This delivery has already been generated and cannot be skipped."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    services._upsert_delivery(
        subscription,
        date,
        quantity=existing.quantity if existing else subscription.quantity,
        status=SubscriptionDelivery.Status.SKIPPED,
    )
    return Response({"date": date.isoformat(), "status": "skipped"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_quantity(request, pk):
    """Override the quantity for a single upcoming date."""
    try:
        subscription = _get_subscription(request, pk)
    except Subscription.DoesNotExist:
        return Response({"error": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = SetQuantitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    date = serializer.validated_data["date"]
    quantity = serializer.validated_data["quantity"]

    if not services.is_change_allowed(date):
        return Response(
            {"error": "The 10 PM cutoff for this delivery date has passed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing = subscription.deliveries.filter(date=date).first()
    if existing and existing.is_generated:
        return Response(
            {"error": "This delivery has already been generated and cannot be changed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    services._upsert_delivery(
        subscription, date, quantity=quantity, status=SubscriptionDelivery.Status.SCHEDULED
    )
    return Response({"date": date.isoformat(), "quantity": quantity})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def vacation(request, pk):
    try:
        subscription = _get_subscription(request, pk)
    except Subscription.DoesNotExist:
        return Response({"error": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = SubscriptionVacationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(subscription=subscription)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


class VacationDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionVacationSerializer
    lookup_url_kwarg = "vacation_id"

    def get_queryset(self):
        return SubscriptionVacation.objects.filter(
            subscription__user=self.request.user, subscription_id=self.kwargs["pk"]
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def calendar(request, pk):
    try:
        subscription = _get_subscription(request, pk)
    except Subscription.DoesNotExist:
        return Response({"error": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)

    month_param = request.query_params.get("month")
    today = datetime.date.today()
    try:
        if month_param:
            year, month = (int(part) for part in month_param.split("-"))
        else:
            year, month = today.year, today.month
        datetime.date(year, month, 1)
    except (ValueError, TypeError):
        return Response(
            {"error": "Invalid 'month' — use YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST
        )

    return Response(
        {"month": f"{year:04d}-{month:02d}", "days": services.calendar(subscription, year, month)}
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def summary(request):
    month_param = request.query_params.get("month")
    today = datetime.date.today()
    try:
        if month_param:
            year, month = (int(part) for part in month_param.split("-"))
        else:
            year, month = today.year, today.month
        datetime.date(year, month, 1)
    except (ValueError, TypeError):
        return Response(
            {"error": "Invalid 'month' — use YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST
        )

    return Response(services.monthly_summary(request.user, year, month))
