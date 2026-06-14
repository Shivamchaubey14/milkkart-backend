import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.notifications.models import Category, DeviceToken, Notification, NotificationPreference
from apps.notifications.services import get_preference, notify

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Test User")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestNotifyService:
    def test_creates_in_app_notification(self, user):
        notification = notify(user, Category.ORDER, "Hi", "Body", data={"k": "v"})
        assert notification is not None
        assert Notification.objects.filter(user=user).count() == 1
        assert notification.data == {"k": "v"}

    def test_auto_creates_preference(self, user):
        notify(user, Category.ORDER, "Hi")
        assert NotificationPreference.objects.filter(user=user).exists()

    def test_promo_suppressed_when_opted_out(self, user):
        pref = get_preference(user)
        pref.promotions = False
        pref.save()
        result = notify(user, Category.PROMO, "Sale!", channels=("push",))
        assert result is None
        assert Notification.objects.filter(user=user).count() == 0

    def test_order_opt_out_keeps_in_app_only(self, user):
        pref = get_preference(user)
        pref.order_updates = False
        pref.save()
        notification = notify(user, Category.ORDER, "Update", channels=("push",))
        assert notification is not None  # still recorded in-app
        assert Notification.objects.filter(user=user).count() == 1

    def test_push_skipped_without_device(self, user):
        # No device token -> PushChannel returns False but notify still records in-app.
        notification = notify(user, Category.ORDER, "Update", channels=("push",))
        assert notification is not None


@pytest.mark.django_db
class TestNotificationAPI:
    def test_list(self, auth_client, user):
        notify(user, Category.ORDER, "One")
        notify(user, Category.SYSTEM, "Two")
        response = auth_client.get(reverse("notification-list"))
        assert response.status_code == 200
        assert len(response.data["results"]) == 2

    def test_user_isolation(self, auth_client, user):
        other = User.objects.create_user(phone="+919999999999", name="Other")
        notify(other, Category.ORDER, "Not yours")
        response = auth_client.get(reverse("notification-list"))
        assert len(response.data["results"]) == 0

    def test_unread_count(self, auth_client, user):
        notify(user, Category.ORDER, "One")
        notify(user, Category.ORDER, "Two")
        response = auth_client.get(reverse("notification-unread-count"))
        assert response.data["unread_count"] == 2

    def test_mark_read(self, auth_client, user):
        n = notify(user, Category.ORDER, "One")
        response = auth_client.post(reverse("notification-read", kwargs={"pk": n.id}))
        assert response.status_code == 200
        assert response.data["is_read"] is True
        assert response.data["read_at"] is not None

    def test_mark_read_not_found(self, auth_client):
        response = auth_client.post(reverse("notification-read", kwargs={"pk": 99999}))
        assert response.status_code == 404

    def test_mark_all_read(self, auth_client, user):
        notify(user, Category.ORDER, "One")
        notify(user, Category.ORDER, "Two")
        response = auth_client.post(reverse("notification-read-all"))
        assert response.data["updated"] == 2
        assert Notification.objects.filter(user=user, is_read=False).count() == 0

    def test_requires_auth(self):
        response = APIClient().get(reverse("notification-list"))
        assert response.status_code == 401


@pytest.mark.django_db
class TestPreferencesAPI:
    def test_get_defaults(self, auth_client):
        response = auth_client.get(reverse("notification-preferences"))
        assert response.status_code == 200
        assert response.data["push_enabled"] is True
        assert response.data["promotions"] is True

    def test_update(self, auth_client, user):
        response = auth_client.put(
            reverse("notification-preferences"), {"promotions": False, "sms_enabled": False}
        )
        assert response.status_code == 200
        assert response.data["promotions"] is False
        pref = get_preference(user)
        assert pref.promotions is False
        assert pref.sms_enabled is False


@pytest.mark.django_db
class TestDeviceRegistration:
    def test_register(self, auth_client, user):
        response = auth_client.post(
            reverse("notification-register-device"), {"token": "abc123", "platform": "ios"}
        )
        assert response.status_code == 201
        device = DeviceToken.objects.get(token="abc123")
        assert device.user == user
        assert device.platform == "ios"

    def test_register_reassigns_token(self, auth_client, user):
        other = User.objects.create_user(phone="+919999999999", name="Other")
        DeviceToken.objects.create(user=other, token="abc123", platform="android")
        auth_client.post(reverse("notification-register-device"), {"token": "abc123"})
        device = DeviceToken.objects.get(token="abc123")
        assert device.user == user  # reassigned to the authenticated user


@pytest.mark.django_db
class TestOrderTaskIntegration:
    def test_status_update_creates_notification(self, user):
        from decimal import Decimal

        from apps.orders.models import Order
        from apps.orders.tasks import send_order_status_update

        order = Order.objects.create(
            user=user, total=Decimal("100.00"), address_snapshot="x", status=Order.Status.DELIVERED
        )
        send_order_status_update(order.id, "delivered")
        notification = Notification.objects.filter(user=user, category=Category.ORDER).first()
        assert notification is not None
        assert notification.title == "Order delivered"
        assert notification.data["status"] == "delivered"
