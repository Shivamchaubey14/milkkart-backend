from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.orders.models import Order
from apps.orders.realtime import broadcast_rider_location
from apps.orders.tasks import send_order_status_update

from .models import DeliveryAssignment
from .permissions import IsRider
from .serializers import (
    DeliverSerializer,
    DeliveryPartnerSerializer,
    DutySerializer,
    LocationSerializer,
    RiderAssignmentSerializer,
)


def _assignment_for(request, order_number):
    return (
        DeliveryAssignment.objects.select_related("order", "rider")
        .filter(order__order_number=order_number, rider__user=request.user)
        .first()
    )


@api_view(["GET", "POST"])
@permission_classes([IsRider])
def rider_duty(request):
    partner = request.user.delivery_partner
    if request.method == "GET":
        return Response(DeliveryPartnerSerializer(partner).data)

    serializer = DutySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    partner.is_on_duty = serializer.validated_data["on_duty"]
    fields = ["is_on_duty", "updated_at"]
    if "lat" in serializer.validated_data and "lng" in serializer.validated_data:
        partner.current_lat = serializer.validated_data["lat"]
        partner.current_lng = serializer.validated_data["lng"]
        partner.last_location_at = timezone.now()
        fields += ["current_lat", "current_lng", "last_location_at"]
    partner.save(update_fields=fields)
    return Response(DeliveryPartnerSerializer(partner).data)


@api_view(["POST"])
@permission_classes([IsRider])
def rider_location(request):
    serializer = LocationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    lat = serializer.validated_data["lat"]
    lng = serializer.validated_data["lng"]

    partner = request.user.delivery_partner
    partner.current_lat = lat
    partner.current_lng = lng
    partner.last_location_at = timezone.now()
    partner.save(update_fields=["current_lat", "current_lng", "last_location_at", "updated_at"])

    # Stream to customers whose order is currently out for delivery with this rider.
    out_for_delivery = DeliveryAssignment.objects.filter(
        rider=partner, status=DeliveryAssignment.Status.PICKED_UP
    ).select_related("order")
    for assignment in out_for_delivery:
        broadcast_rider_location(assignment.order.order_number, lat, lng)

    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([IsRider])
def rider_assignments(request):
    assignments = (
        DeliveryAssignment.objects.filter(rider__user=request.user)
        .exclude(status__in=[DeliveryAssignment.Status.DELIVERED, DeliveryAssignment.Status.CANCELLED])
        .select_related("order")
    )
    return Response(RiderAssignmentSerializer(assignments, many=True).data)


@api_view(["POST"])
@permission_classes([IsRider])
def accept_order(request, order_number):
    assignment = _assignment_for(request, order_number)
    if assignment is None:
        return Response({"error": "Assignment not found."}, status=status.HTTP_404_NOT_FOUND)
    if assignment.status != DeliveryAssignment.Status.ASSIGNED:
        return Response({"error": "Assignment cannot be accepted."}, status=status.HTTP_400_BAD_REQUEST)

    assignment.status = DeliveryAssignment.Status.ACCEPTED
    assignment.accepted_at = timezone.now()
    assignment.save(update_fields=["status", "accepted_at"])
    return Response(RiderAssignmentSerializer(assignment).data)


@api_view(["POST"])
@permission_classes([IsRider])
def pickup_order(request, order_number):
    assignment = _assignment_for(request, order_number)
    if assignment is None:
        return Response({"error": "Assignment not found."}, status=status.HTTP_404_NOT_FOUND)
    if assignment.status not in (DeliveryAssignment.Status.ASSIGNED, DeliveryAssignment.Status.ACCEPTED):
        return Response({"error": "Order is not ready for pickup."}, status=status.HTTP_400_BAD_REQUEST)

    assignment.status = DeliveryAssignment.Status.PICKED_UP
    assignment.picked_up_at = timezone.now()
    assignment.save(update_fields=["status", "picked_up_at"])

    order = assignment.order
    order.status = Order.Status.OUT_FOR_DELIVERY
    order.save(update_fields=["status"])
    send_order_status_update.delay(order.id, Order.Status.OUT_FOR_DELIVERY)

    return Response(RiderAssignmentSerializer(assignment).data)


@api_view(["POST"])
@permission_classes([IsRider])
def deliver_order(request, order_number):
    serializer = DeliverSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    assignment = _assignment_for(request, order_number)
    if assignment is None:
        return Response({"error": "Assignment not found."}, status=status.HTTP_404_NOT_FOUND)
    if assignment.status != DeliveryAssignment.Status.PICKED_UP:
        return Response({"error": "Order is not out for delivery."}, status=status.HTTP_400_BAD_REQUEST)
    if serializer.validated_data["otp"] != assignment.delivery_otp:
        return Response({"error": "Incorrect delivery OTP."}, status=status.HTTP_400_BAD_REQUEST)

    assignment.status = DeliveryAssignment.Status.DELIVERED
    assignment.delivered_at = timezone.now()
    assignment.proof_photo = serializer.validated_data.get("proof_photo", "")
    assignment.save(update_fields=["status", "delivered_at", "proof_photo"])

    order = assignment.order
    order.status = Order.Status.DELIVERED
    order.save(update_fields=["status"])
    send_order_status_update.delay(order.id, Order.Status.DELIVERED)

    return Response(RiderAssignmentSerializer(assignment).data)
