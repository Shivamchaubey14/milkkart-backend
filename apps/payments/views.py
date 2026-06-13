from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.orders.models import Order
from apps.orders.tasks import send_order_confirmation

from . import gateway
from .models import Payment
from .serializers import InitiatePaymentSerializer, PaymentSerializer, VerifyPaymentSerializer
from .tasks import send_payment_receipt


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    serializer = InitiatePaymentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        order = Order.objects.get(
            order_number=serializer.validated_data["order_number"],
            user=request.user,
        )
    except Order.DoesNotExist:
        return Response({"error": "Order not found."}, status=status.HTTP_400_BAD_REQUEST)

    if order.status != Order.Status.PENDING:
        return Response(
            {"error": "Order is not awaiting payment."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if hasattr(order, "payment") and order.payment.status in (
        Payment.Status.PENDING,
        Payment.Status.SUCCESS,
    ):
        return Response(
            {"error": "Payment already initiated for this order."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    method = serializer.validated_data["method"]

    with transaction.atomic():
        # Replace any prior created/failed attempt for this order.
        Payment.objects.filter(order=order).delete()

        if method == Payment.Method.COD:
            payment = Payment.objects.create(
                order=order,
                user=request.user,
                method=method,
                status=Payment.Status.PENDING,
                amount=order.total,
            )
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=["status"])
        else:
            gateway_order = gateway.create_gateway_order(order.total, receipt=order.order_number)
            payment = Payment.objects.create(
                order=order,
                user=request.user,
                method=method,
                status=Payment.Status.CREATED,
                amount=order.total,
                gateway_order_id=gateway_order["id"],
            )

    if method == Payment.Method.COD:
        send_payment_receipt.delay(payment.id)
        send_order_confirmation.delay(order.id)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    data = PaymentSerializer(payment).data
    data["gateway"] = {
        "key_id": gateway_order["key_id"],
        "order_id": gateway_order["id"],
        "amount": gateway_order["amount"],
        "currency": gateway_order["currency"],
    }
    return Response(data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    serializer = VerifyPaymentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    gateway_order_id = serializer.validated_data["gateway_order_id"]

    try:
        payment = Payment.objects.select_related("order").get(
            gateway_order_id=gateway_order_id,
            user=request.user,
        )
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found."}, status=status.HTTP_400_BAD_REQUEST)

    if payment.status == Payment.Status.SUCCESS:
        return Response(PaymentSerializer(payment).data)

    gateway_payment_id = serializer.validated_data["gateway_payment_id"]
    gateway_signature = serializer.validated_data["gateway_signature"]

    if not gateway.verify_signature(gateway_order_id, gateway_payment_id, gateway_signature):
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status", "updated_at"])
        return Response(
            {"error": "Payment signature verification failed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        payment.gateway_payment_id = gateway_payment_id
        payment.gateway_signature = gateway_signature
        payment.status = Payment.Status.SUCCESS
        payment.save(update_fields=["gateway_payment_id", "gateway_signature", "status", "updated_at"])

        order = payment.order
        if order.status == Order.Status.PENDING:
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=["status"])

    send_payment_receipt.delay(payment.id)
    send_order_confirmation.delay(payment.order_id)

    return Response(PaymentSerializer(payment).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_detail(request, order_number):
    try:
        payment = Payment.objects.select_related("order").get(
            order__order_number=order_number,
            user=request.user,
        )
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(PaymentSerializer(payment).data)
