import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def send_order_confirmation(order_id):
    """Send order confirmation notification. Plug in SMS/email/push here."""
    from .models import Order

    try:
        order = Order.objects.select_related("user").get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order %s not found for confirmation", order_id)
        return

    logger.info(
        "[NOTIFICATION] Order %s confirmed for %s — total: %s",
        order.order_number,
        order.user.phone,
        order.total,
    )
    return {"order_id": order_id, "status": "confirmation_sent"}


@shared_task
def send_order_status_update(order_id, new_status):
    """Notify user of order status change."""
    from .models import Order

    try:
        order = Order.objects.select_related("user").get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order %s not found for status update", order_id)
        return

    logger.info(
        "[NOTIFICATION] Order %s status → %s for %s",
        order.order_number,
        new_status,
        order.user.phone,
    )
    return {"order_id": order_id, "new_status": new_status, "status": "notification_sent"}
