import json

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.orders.models import Order
from apps.orders.tasks import send_order_confirmation
from apps.wallet.models import InsufficientBalance, get_or_create_wallet

from . import gateway, services
from .models import Payment, PaymentWebhookEvent
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

    if method == Payment.Method.WALLET:
        wallet = get_or_create_wallet(request.user)
        if wallet.balance < order.total:
            return Response(
                {"error": "Insufficient wallet balance."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        elif method == Payment.Method.WALLET:
            try:
                wallet.debit(order.total, description=f"Order {order.order_number}", order=order)
            except InsufficientBalance:
                transaction.set_rollback(True)
                return Response(
                    {"error": "Insufficient wallet balance."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            payment = Payment.objects.create(
                order=order,
                user=request.user,
                method=method,
                status=Payment.Status.SUCCESS,
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

    if method in (Payment.Method.COD, Payment.Method.WALLET):
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


def _entity(event, key):
    return event.get("payload", {}).get(key, {}).get("entity", {})


def _derive_event_id(event_type, event):
    """Fallback idempotency key when the gateway sends no event-id header."""
    entity = _entity(event, "payment") or _entity(event, "refund")
    return f"{event_type}:{entity.get('id', '')}"


def _dispatch_event(event_type, event):
    if event_type in ("payment.captured", "payment.authorized"):
        entity = _entity(event, "payment")
        return services.capture(entity.get("order_id", ""), entity.get("id", ""))
    if event_type == "payment.failed":
        entity = _entity(event, "payment")
        return services.mark_failed(entity.get("order_id", ""))
    if event_type in ("refund.processed", "refund.created"):
        entity = _entity(event, "refund")
        return services.mark_refunded(entity.get("payment_id", ""))
    return "ignored"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([])
def webhook(request):
    """Authoritative async confirmation from the gateway.

    Verifies the signature over the raw body, dedupes by event id, then applies the
    state transition. Handlers are idempotent, so a replay is harmless.
    """
    raw = request.body
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not gateway.verify_webhook_signature(raw, signature):
        return Response({"error": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        return Response({"error": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST)

    event_type = event.get("event", "")
    event_id = request.headers.get("X-Razorpay-Event-Id") or _derive_event_id(event_type, event)

    log, created = PaymentWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={"event_type": event_type, "payload": event},
    )
    if not created and log.processed:
        return Response({"status": "duplicate"})

    result = _dispatch_event(event_type, event)

    log.processed = True
    log.event_type = event_type
    log.save(update_fields=["processed", "event_type"])
    return Response({"status": result})


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
