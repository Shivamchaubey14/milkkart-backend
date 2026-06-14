import logging

from celery import shared_task

from .realtime import broadcast_order_status

logger = logging.getLogger(__name__)

STATUS_MESSAGES = {
    "pending": ("Order placed", "We've received order {num} — it's awaiting payment."),
    "confirmed": ("Order confirmed", "Order {num} is confirmed and being prepared."),
    "out_for_delivery": ("Out for delivery", "Order {num} is on its way!"),
    "delivered": ("Order delivered", "Order {num} has been delivered. Enjoy!"),
    "cancelled": ("Order cancelled", "Order {num} has been cancelled."),
}


def _notify_order(order):
    from apps.notifications.models import Category
    from apps.notifications.services import notify

    title, body = STATUS_MESSAGES.get(order.status, ("Order update", "Order {num} was updated."))
    notify(
        order.user,
        Category.ORDER,
        title,
        body.format(num=order.order_number),
        data={"order_number": str(order.order_number), "status": order.status},
        channels=("push", "sms"),
    )


@shared_task
def send_order_confirmation(order_id):
    """Notify the customer about a placed/confirmed order (in-app + push/SMS + WebSocket)."""
    from .models import Order

    try:
        order = Order.objects.select_related("user").get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order %s not found for confirmation", order_id)
        return

    _notify_order(order)
    broadcast_order_status(order)
    return {"order_id": order_id, "status": "confirmation_sent"}


@shared_task
def send_order_status_update(order_id, new_status):
    """Notify the customer of an order status change (in-app + push/SMS + WebSocket)."""
    from .models import Order

    try:
        order = Order.objects.select_related("user").get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order %s not found for status update", order_id)
        return

    _notify_order(order)
    broadcast_order_status(order)
    return {"order_id": order_id, "new_status": new_status, "status": "notification_sent"}
