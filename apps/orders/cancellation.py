"""Shared order-cancellation logic used by both the customer and admin endpoints.

Returns stock to inventory, frees the booked delivery slot, settles the payment
(wallet refund inline, gateway refund enqueued by the caller) and marks the order
cancelled — all in one transaction.
"""

from django.db import transaction

from apps.inventory.models import StockMovement
from apps.inventory.services import adjust_stock

from .models import Order

# Orders may be cancelled (by customer or ops) up to and including CONFIRMED.
CANCELLABLE_STATUSES = (Order.Status.PENDING, Order.Status.CONFIRMED)


def perform_cancellation(order, actor):
    """Cancel ``order`` and settle side effects.

    The caller must have checked ``order.status`` is cancellable. Returns the
    payment id to refund via the gateway (``process_refund``), or ``None`` when
    nothing needs an async refund (wallet refunds settle inline here).
    """
    from apps.delivery.models import DeliveryAssignment
    from apps.payments.models import Payment
    from apps.wallet.models import WalletTransaction, get_or_create_wallet

    refund_payment_id = None
    with transaction.atomic():
        # Stand down any active rider assignment so it leaves the rider's queue.
        try:
            assignment = order.assignment
        except DeliveryAssignment.DoesNotExist:
            assignment = None
        if assignment and assignment.status not in (
            DeliveryAssignment.Status.DELIVERED,
            DeliveryAssignment.Status.CANCELLED,
        ):
            assignment.status = DeliveryAssignment.Status.CANCELLED
            assignment.save(update_fields=["status"])

        # Return reserved stock through the inventory ledger.
        for item in order.items.all():
            if item.variant:
                adjust_stock(
                    item.variant,
                    item.quantity,
                    StockMovement.Reason.CANCELLATION,
                    order=order,
                    user=actor,
                    lock=False,
                )

        # Free the booked delivery slot.
        if order.delivery_slot and order.delivery_slot.booked > 0:
            order.delivery_slot.booked -= 1
            order.delivery_slot.save(update_fields=["booked"])

        # Settle payment: refund if captured, otherwise void.
        payment = getattr(order, "payment", None)
        if payment:
            if payment.status == Payment.Status.SUCCESS:
                payment.status = Payment.Status.REFUNDED
                payment.save(update_fields=["status", "updated_at"])
                if payment.method == Payment.Method.WALLET:
                    wallet = get_or_create_wallet(order.user)
                    wallet.credit(
                        payment.amount,
                        WalletTransaction.Type.REFUND,
                        description=f"Refund for order {order.order_number}",
                        order=order,
                    )
                else:
                    refund_payment_id = payment.id
            elif payment.status in (Payment.Status.CREATED, Payment.Status.PENDING):
                payment.status = Payment.Status.FAILED
                payment.save(update_fields=["status", "updated_at"])

        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])

    return refund_payment_id
