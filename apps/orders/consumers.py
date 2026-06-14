import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Order
from .realtime import order_group_name, order_status_payload


class OrderTrackingConsumer(AsyncWebsocketConsumer):
    """Streams live status (and, later, rider location) for a single order to its owner."""

    async def connect(self):
        self.user = self.scope["user"]
        self.order_number = self.scope["url_route"]["kwargs"]["order_number"]

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        order = await self._get_order()
        if order is None:
            await self.close(code=4404)
            return

        self.group_name = order_group_name(self.order_number)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        # Send the current status immediately so the client can render on connect.
        await self.send(text_data=json.dumps(order_status_payload(order)))

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def order_status(self, event):
        await self.send(text_data=json.dumps(event["payload"]))

    async def rider_location(self, event):
        await self.send(text_data=json.dumps(event["payload"]))

    @database_sync_to_async
    def _get_order(self):
        return Order.objects.filter(order_number=self.order_number, user=self.user).first()
