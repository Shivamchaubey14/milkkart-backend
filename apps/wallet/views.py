import uuid

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.payments import gateway
from apps.payments.upi import upi_payload

from .models import WalletTopup, WalletTransaction, get_or_create_wallet
from .serializers import TopupSerializer, TopupVerifySerializer, WalletSerializer, WalletTransactionSerializer


class _TopupThrottle(ScopedRateThrottle):
    scope = "topup"


class _TopupStatusThrottle(ScopedRateThrottle):
    scope = "topup_status"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def wallet_detail(request):
    wallet = get_or_create_wallet(request.user)
    return Response(WalletSerializer(wallet).data)


class WalletTransactionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WalletTransactionSerializer

    def get_queryset(self):
        wallet = get_or_create_wallet(self.request.user)
        return WalletTransaction.objects.filter(wallet=wallet).select_related("order")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([_TopupThrottle])
def wallet_topup(request):
    serializer = TopupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    amount = serializer.validated_data["amount"]

    wallet = get_or_create_wallet(request.user)
    topup = WalletTopup.objects.create(wallet=wallet, amount=amount)
    gateway_order = gateway.create_gateway_order(amount, receipt=f"topup-{topup.id}")
    topup.gateway_order_id = gateway_order["id"]
    topup.save(update_fields=["gateway_order_id"])

    return Response(
        {
            "topup_id": topup.id,
            "amount": amount,
            "status": topup.status,
            # Gateway-agnostic UPI intent/QR — any UPI app can pay this without a
            # specific gateway. Reconciles on the gateway order id (tr=...).
            "upi": upi_payload(amount, topup.gateway_order_id),
            "gateway": {
                "provider": gateway.provider(),
                "key_id": gateway_order["key_id"],
                "order_id": gateway_order["id"],
                "amount": gateway_order["amount"],
                "currency": gateway_order["currency"],
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([_TopupStatusThrottle])
def wallet_topup_status(request, pk):
    """Report a top-up's status — read-only, never credits.

    A wallet is credited ONLY by an authenticated payment confirmation: the
    gateway webhook or signature verify (``/topup/verify/``) in production, or the
    explicit dev mock-pay. Polling this endpoint must never move money — otherwise
    a top-up would credit without the customer actually paying.
    """
    wallet = get_or_create_wallet(request.user)
    try:
        topup = WalletTopup.objects.get(pk=pk, wallet=wallet)
    except WalletTopup.DoesNotExist:
        return Response({"error": "Top-up not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(
        {
            "topup_id": topup.id,
            "status": topup.status,
            "wallet": WalletSerializer(wallet).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_topup_verify(request):
    serializer = TopupVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    wallet = get_or_create_wallet(request.user)
    gateway_order_id = serializer.validated_data["gateway_order_id"]

    try:
        topup = WalletTopup.objects.get(gateway_order_id=gateway_order_id, wallet=wallet)
    except WalletTopup.DoesNotExist:
        return Response({"error": "Top-up not found."}, status=status.HTTP_400_BAD_REQUEST)

    if topup.status == WalletTopup.Status.SUCCESS:
        return Response(WalletSerializer(wallet).data)

    gateway_payment_id = serializer.validated_data["gateway_payment_id"]
    gateway_signature = serializer.validated_data["gateway_signature"]

    if not gateway.verify_signature(gateway_order_id, gateway_payment_id, gateway_signature):
        topup.status = WalletTopup.Status.FAILED
        topup.save(update_fields=["status", "updated_at"])
        return Response(
            {"error": "Payment signature verification failed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    topup.gateway_payment_id = gateway_payment_id
    topup.status = WalletTopup.Status.SUCCESS
    topup.save(update_fields=["gateway_payment_id", "status", "updated_at"])
    wallet.credit(topup.amount, WalletTransaction.Type.TOPUP, description="Wallet top-up")

    return Response(WalletSerializer(wallet).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_topup_mock_pay(request):
    """Simulate a successful gateway payment for a created top-up.

    Dev/demo only (mock gateway): a real client receives the payment id + signature
    from the gateway's checkout widget; this stands in for that so top-ups complete
    without a live gateway. Disabled when a real gateway is configured.
    """
    import uuid

    from django.conf import settings

    if getattr(settings, "PAYMENT_GATEWAY", "mock") != "mock":
        return Response(
            {"error": "Mock payment is disabled with a live gateway."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    wallet = get_or_create_wallet(request.user)
    order_id = request.data.get("gateway_order_id")
    try:
        topup = WalletTopup.objects.get(gateway_order_id=order_id, wallet=wallet)
    except WalletTopup.DoesNotExist:
        return Response({"error": "Top-up not found."}, status=status.HTTP_400_BAD_REQUEST)

    if topup.status != WalletTopup.Status.SUCCESS:
        topup.gateway_payment_id = "pay_mock_" + uuid.uuid4().hex[:14]
        topup.status = WalletTopup.Status.SUCCESS
        topup.save(update_fields=["gateway_payment_id", "status", "updated_at"])
        wallet.credit(topup.amount, WalletTransaction.Type.TOPUP, description="Wallet top-up")

    return Response(WalletSerializer(wallet).data)
