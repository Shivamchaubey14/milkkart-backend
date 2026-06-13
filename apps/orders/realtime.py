"""Helpers for broadcasting order updates over the Channels layer."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

GROUP_EVENT = "order.status"


def order_group_name(order_number):
    return f"order_{order_number}"


def order_status_payload(order):
    return {
        "type": "order.status",
        "order_number": str(order.order_number),
        "status": order.status,
        "status_display": order.get_status_display(),
    }


def broadcast_order_status(order):
    """Push the order's current status to everyone tracking it. No-op if no layer."""
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        order_group_name(order.order_number),
        {"type": GROUP_EVENT, "payload": order_status_payload(order)},
    )
