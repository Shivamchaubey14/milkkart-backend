"""Ops order board (FR-ADM-04): list every order, confirm, cancel (with refund),
and assign a rider (manually or auto-suggested). Guarded by the ops/admin role.
"""

from datetime import datetime, time

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsOpsManager
from apps.delivery.models import DeliveryAssignment, DeliveryPartner
from apps.delivery.services import NoRiderAvailable, assign_order

from .admin_serializers import AdminOrderDetailSerializer, AdminOrderSerializer
from .cancellation import CANCELLABLE_STATUSES, perform_cancellation
from .models import Order
from .tasks import send_order_status_update

_BOARD_QS = Order.objects.select_related("user", "assignment__rider__user").prefetch_related("items")
_DETAIL_QS = Order.objects.select_related("user", "coupon", "assignment__rider__user").prefetch_related(
    "items__variant__product__images"
)


def _get(order_number):
    return _BOARD_QS.filter(order_number=order_number).first()


@api_view(["GET"])
@permission_classes([IsOpsManager])
def order_board(request):
    qs = _BOARD_QS.order_by("-placed_at")
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)
    # Filter by an explicit timezone-aware datetime range rather than a
    # ``placed_at__date`` lookup: that lookup relies on the DB time-zone tables
    # (CONVERT_TZ), which aren't loaded on MySQL here and would match nothing.
    start = _parse_date(request.query_params.get("start"))
    end = _parse_date(request.query_params.get("end"))
    if start:
        qs = qs.filter(placed_at__gte=timezone.make_aware(datetime.combine(start, time.min)))
    if end:
        qs = qs.filter(placed_at__lte=timezone.make_aware(datetime.combine(end, time.max)))
    return Response(AdminOrderSerializer(qs, many=True).data)


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@api_view(["GET"])
@permission_classes([IsOpsManager])
def order_detail(request, order_number):
    order = _DETAIL_QS.filter(order_number=order_number).first()
    if order is None:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(AdminOrderDetailSerializer(order, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsOpsManager])
def confirm_order(request, order_number):
    order = _get(order_number)
    if order is None:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
    if order.status != Order.Status.PENDING:
        return Response({"error": "Only pending orders can be confirmed."}, status=status.HTTP_400_BAD_REQUEST)

    order.status = Order.Status.CONFIRMED
    order.save(update_fields=["status"])
    send_order_status_update.delay(order.id, Order.Status.CONFIRMED)
    return Response(AdminOrderSerializer(_get(order_number)).data)


@api_view(["POST"])
@permission_classes([IsOpsManager])
def cancel_order(request, order_number):
    from apps.payments.tasks import process_refund

    order = _get(order_number)
    if order is None:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
    if order.status not in CANCELLABLE_STATUSES:
        return Response(
            {"error": f"Order cannot be cancelled once it is {order.get_status_display().lower()}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    refund_payment_id = perform_cancellation(order, request.user)
    if refund_payment_id:
        process_refund.delay(refund_payment_id)
    send_order_status_update.delay(order.id, Order.Status.CANCELLED)
    return Response(AdminOrderSerializer(_get(order_number)).data)


@api_view(["POST"])
@permission_classes([IsOpsManager])
def assign_rider(request, order_number):
    order = _get(order_number)
    if order is None:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
    if order.status != Order.Status.CONFIRMED:
        return Response({"error": "Only confirmed orders can be assigned."}, status=status.HTTP_400_BAD_REQUEST)
    if DeliveryAssignment.objects.filter(order=order).exists():
        return Response({"error": "Order is already assigned."}, status=status.HTTP_400_BAD_REQUEST)

    rider = None
    rider_id = request.data.get("rider_id")
    if rider_id:
        rider = DeliveryPartner.objects.filter(id=rider_id, is_active=True).first()
        if rider is None:
            return Response({"error": "Rider not found."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        assign_order(order, rider)  # auto-picks the least-loaded on-duty rider when rider is None
    except NoRiderAvailable as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(AdminOrderSerializer(_get(order_number)).data)
