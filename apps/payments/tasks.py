import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def send_payment_receipt(payment_id):
    """Send a payment receipt notification. Plug in SMS/email/push here."""
    from .models import Payment

    try:
        payment = Payment.objects.select_related("user", "order").get(id=payment_id)
    except Payment.DoesNotExist:
        logger.error("Payment %s not found for receipt", payment_id)
        return

    logger.info(
        "[NOTIFICATION] Payment %s %s for order %s — %s paid by %s",
        payment.payment_id,
        payment.status,
        payment.order.order_number,
        payment.amount,
        payment.user.phone,
    )
    return {"payment_id": payment_id, "status": "receipt_sent"}
