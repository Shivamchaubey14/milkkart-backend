from decimal import Decimal

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing.websocket import WebsocketCommunicator
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.channels_auth import JWTAuthMiddlewareStack
from apps.orders.models import Order
from apps.orders.realtime import order_group_name, order_status_payload
from apps.orders.routing import websocket_urlpatterns

User = get_user_model()

application = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))


@database_sync_to_async
def create_user_and_order(phone="+919876543210"):
    user = User.objects.create_user(phone=phone, name="Tracker")
    order = Order.objects.create(user=user, total=Decimal("100.00"), address_snapshot="x")
    token = str(AccessToken.for_user(user))
    return user, order, token


async def open_ws(order_number, token=None):
    url = f"/ws/orders/{order_number}/"
    if token:
        url += f"?token={token}"
    communicator = WebsocketCommunicator(application, url)
    connected, _ = await communicator.connect()
    return communicator, connected


@pytest.mark.django_db(transaction=True)
class TestOrderTrackingConsumer:
    async def test_connect_sends_initial_status(self):
        _, order, token = await create_user_and_order()
        communicator, connected = await open_ws(order.order_number, token)
        assert connected is True
        frame = await communicator.receive_json_from()
        assert frame["order_number"] == str(order.order_number)
        assert frame["status"] == "pending"
        await communicator.disconnect()

    async def test_rejects_without_token(self):
        _, order, _ = await create_user_and_order()
        communicator, connected = await open_ws(order.order_number, token=None)
        assert connected is False
        await communicator.disconnect()

    async def test_rejects_other_users_order(self):
        _, order, _ = await create_user_and_order()
        _, _, other_token = await create_user_and_order(phone="+919999999999")
        communicator, connected = await open_ws(order.order_number, other_token)
        assert connected is False
        await communicator.disconnect()

    async def test_rejects_unknown_order(self):
        _, _, token = await create_user_and_order()
        communicator, connected = await open_ws("00000000-0000-0000-0000-000000000000", token)
        assert connected is False
        await communicator.disconnect()

    async def test_receives_status_broadcast(self):
        _, order, token = await create_user_and_order()
        communicator, connected = await open_ws(order.order_number, token)
        assert connected is True
        await communicator.receive_json_from()  # initial frame

        order.status = Order.Status.OUT_FOR_DELIVERY
        layer = get_channel_layer()
        await layer.group_send(
            order_group_name(order.order_number),
            {"type": "order.status", "payload": order_status_payload(order)},
        )

        frame = await communicator.receive_json_from()
        assert frame["status"] == "out_for_delivery"
        assert frame["status_display"] == "Out for Delivery"
        await communicator.disconnect()

    async def test_receives_rider_location(self):
        _, order, token = await create_user_and_order()
        communicator, connected = await open_ws(order.order_number, token)
        assert connected is True
        await communicator.receive_json_from()  # initial status

        layer = get_channel_layer()
        await layer.group_send(
            order_group_name(order.order_number),
            {
                "type": "rider.location",
                "payload": {
                    "type": "rider.location",
                    "order_number": str(order.order_number),
                    "lat": "26.449923",
                    "lng": "80.331871",
                },
            },
        )

        frame = await communicator.receive_json_from()
        assert frame["type"] == "rider.location"
        assert frame["lat"] == "26.449923"
        await communicator.disconnect()


@pytest.mark.django_db
class TestRealtimeHelpers:
    def test_order_group_name(self):
        assert order_group_name("abc") == "order_abc"

    def test_status_payload(self, db):
        user = User.objects.create_user(phone="+919811111111", name="P")
        order = Order.objects.create(user=user, total=Decimal("10.00"), address_snapshot="x")
        payload = order_status_payload(order)
        assert payload["type"] == "order.status"
        assert payload["status"] == "pending"
        assert payload["status_display"] == "Pending"
        assert payload["order_number"] == str(order.order_number)
