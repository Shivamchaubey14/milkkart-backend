"""Authoritative payment state transitions, shared by the verify views and the
webhook. Every transition is idempotent so the client callback and the gateway
webhook can both arrive without double-applying.

Reconciliation keys on ``gateway_order_id``, which belongs to either an order
:class:`Payment` or a :class:`~apps.wallet.models.WalletTopup`.
"""

import logging

from django.db import transaction

from apps.orders.models import Order
from apps.wallet.models import WalletTopup, WalletTransaction, get_or_create_wallet

from .models import Payment

logger = logging.getLogger(__name__)


def capture(gateway_order_id, gateway_payment_id=""):
    """Mark the order payment or wallet top-up for ``gateway_order_id`` as successful.

    Returns a short string describing what happened (for logging/telemetry).
    """
    payment = (
        Payment.objects.select_related("order").filter(gateway_order_id=gateway_order_id).first()
    )
    if payment:
        return _capture_order_payment(payment, gateway_payment_id)

    topup = WalletTopup.objects.select_related("wallet").filter(
        gateway_order_id=gateway_order_id
    ).first()
    if topup:
        return _capture_topup(topup, gateway_payment_id)

    logger.warning("Webhook capture: no payment/topup for order %s", gateway_order_id)
    return "unmatched"


def _capture_order_payment(payment, gateway_payment_id):
    if payment.status == Payment.Status.SUCCESS:
        return "payment_already_captured"

    from apps.orders.tasks import send_order_confirmation

    from .tasks import send_payment_receipt

    with transaction.atomic():
        payment.status = Payment.Status.SUCCESS
        if gateway_payment_id:
            payment.gateway_payment_id = gateway_payment_id
        payment.save(update_fields=["status", "gateway_payment_id", "updated_at"])

        order = payment.order
        if order.status == Order.Status.PENDING:
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=["status"])

    send_payment_receipt.delay(payment.id)
    send_order_confirmation.delay(payment.order_id)
    return "payment_captured"


def _capture_topup(topup, gateway_payment_id):
    if topup.status == WalletTopup.Status.SUCCESS:
        return "topup_already_captured"

    with transaction.atomic():
        topup.status = WalletTopup.Status.SUCCESS
        if gateway_payment_id:
            topup.gateway_payment_id = gateway_payment_id
        topup.save(update_fields=["status", "gateway_payment_id", "updated_at"])

        wallet = get_or_create_wallet(topup.wallet.user)
        wallet.credit(topup.amount, WalletTransaction.Type.TOPUP, description="Wallet top-up")
    return "topup_captured"


def mark_failed(gateway_order_id):
    """Mark a still-open order payment or top-up as failed (idempotent)."""
    payment = Payment.objects.filter(gateway_order_id=gateway_order_id).first()
    if payment:
        if payment.status in (Payment.Status.CREATED, Payment.Status.PENDING):
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
        return "payment_failed"

    topup = WalletTopup.objects.filter(gateway_order_id=gateway_order_id).first()
    if topup:
        if topup.status in (WalletTopup.Status.CREATED,):
            topup.status = WalletTopup.Status.FAILED
            topup.save(update_fields=["status", "updated_at"])
        return "topup_failed"
    return "unmatched"


def mark_refunded(gateway_payment_id):
    """Record a gateway-side refund against a captured order payment (idempotent)."""
    payment = Payment.objects.filter(gateway_payment_id=gateway_payment_id).first()
    if not payment:
        return "unmatched"
    if payment.status != Payment.Status.REFUNDED:
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status", "updated_at"])
    return "payment_refunded"
