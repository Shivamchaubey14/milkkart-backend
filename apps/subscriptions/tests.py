import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.addresses.models import Address
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import Order
from apps.wallet.models import WalletTransaction, get_or_create_wallet

from . import services
from .models import Subscription, SubscriptionDelivery, SubscriptionVacation
from .tasks import send_low_balance_reminders

User = get_user_model()

MONDAY = datetime.date(2026, 6, 15)  # a known Monday


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Sub User")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def address(user):
    return Address.objects.create(
        user=user,
        address_line="12 Dairy Lane",
        city="Pune",
        state="MH",
        pincode="411001",
    )


@pytest.fixture
def variant(db):
    category = Category.objects.create(name="Milk")
    product = Product.objects.create(category=category, name="Full Cream Milk")
    return ProductVariant.objects.create(
        product=product,
        label="500 ml",
        sku="MILK-500",
        price=Decimal("30.00"),
        mrp=Decimal("32.00"),
        stock=100,
    )


@pytest.fixture
def subscription(user, variant, address):
    return Subscription.objects.create(
        user=user,
        variant=variant,
        quantity=2,
        frequency=Subscription.Frequency.DAILY,
        address=address,
        start_date=MONDAY,
    )


def fund(user, amount):
    wallet = get_or_create_wallet(user)
    wallet.credit(Decimal(amount), WalletTransaction.Type.TOPUP, description="test top-up")
    return wallet


# --------------------------------------------------------------------------- #
# Schedule logic
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestIsDue:
    def test_daily(self, subscription):
        assert services.is_due(subscription, MONDAY)
        assert services.is_due(subscription, MONDAY + datetime.timedelta(days=1))

    def test_before_start_date(self, subscription):
        assert not services.is_due(subscription, MONDAY - datetime.timedelta(days=1))

    def test_weekdays_skips_weekend(self, subscription):
        subscription.frequency = Subscription.Frequency.WEEKDAYS
        subscription.save()
        saturday = MONDAY + datetime.timedelta(days=5)
        assert services.is_due(subscription, MONDAY)  # Monday
        assert not services.is_due(subscription, saturday)

    def test_alternate_days(self, subscription):
        subscription.frequency = Subscription.Frequency.ALTERNATE
        subscription.save()
        assert services.is_due(subscription, MONDAY)
        assert not services.is_due(subscription, MONDAY + datetime.timedelta(days=1))
        assert services.is_due(subscription, MONDAY + datetime.timedelta(days=2))

    def test_custom_dates(self, subscription):
        target = MONDAY + datetime.timedelta(days=3)
        subscription.frequency = Subscription.Frequency.CUSTOM
        subscription.custom_days = [target.isoformat()]
        subscription.save()
        assert services.is_due(subscription, target)
        assert not services.is_due(subscription, MONDAY)

    def test_paused_never_due(self, subscription):
        subscription.status = Subscription.Status.PAUSED
        subscription.save()
        assert not services.is_due(subscription, MONDAY)

    def test_vacation_skips(self, subscription):
        SubscriptionVacation.objects.create(
            subscription=subscription,
            start_date=MONDAY,
            end_date=MONDAY + datetime.timedelta(days=3),
        )
        assert not services.is_due(subscription, MONDAY + datetime.timedelta(days=1))
        assert services.is_due(subscription, MONDAY + datetime.timedelta(days=4))


@pytest.mark.django_db
class TestCutoff:
    def test_future_date_allowed(self):
        far = datetime.date.today() + datetime.timedelta(days=5)
        assert services.is_change_allowed(far)

    def test_today_is_past_cutoff(self):
        # The cutoff for today was 10 PM yesterday — always passed.
        assert not services.is_change_allowed(datetime.date.today())


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestGeneration:
    def test_success_charges_wallet_and_creates_order(self, subscription, variant):
        fund(subscription.user, "100")
        delivery = services.generate_for_subscription(subscription, MONDAY)

        assert delivery.status == SubscriptionDelivery.Status.SCHEDULED
        assert delivery.is_generated
        # 2 x 30 = 60 + 5% tax = 63
        assert delivery.amount == Decimal("63.00")
        order = delivery.order
        assert order.status == Order.Status.CONFIRMED
        assert order.total == Decimal("63.00")
        assert order.items.count() == 1

        wallet = get_or_create_wallet(subscription.user)
        assert wallet.balance == Decimal("37.00")
        variant.refresh_from_db()
        assert variant.stock == 98

    def test_insufficient_balance_flags_and_does_not_charge(self, subscription, variant):
        fund(subscription.user, "10")  # < 63
        delivery = services.generate_for_subscription(subscription, MONDAY)

        assert delivery.status == SubscriptionDelivery.Status.FAILED_BALANCE
        assert delivery.order is None
        wallet = get_or_create_wallet(subscription.user)
        assert wallet.balance == Decimal("10.00")  # untouched — order rolled back
        variant.refresh_from_db()
        assert variant.stock == 100
        assert not Order.objects.exists()

    def test_out_of_stock_skips(self, subscription, variant):
        fund(subscription.user, "100")
        variant.stock = 1  # need 2
        variant.save()
        delivery = services.generate_for_subscription(subscription, MONDAY)

        assert delivery.status == SubscriptionDelivery.Status.SKIPPED
        assert delivery.order is None
        wallet = get_or_create_wallet(subscription.user)
        assert wallet.balance == Decimal("100.00")

    def test_idempotent_no_double_charge(self, subscription):
        fund(subscription.user, "200")
        first = services.generate_for_subscription(subscription, MONDAY)
        second = services.generate_for_subscription(subscription, MONDAY)
        assert first.pk == second.pk
        assert Order.objects.count() == 1
        wallet = get_or_create_wallet(subscription.user)
        assert wallet.balance == Decimal("137.00")

    def test_skip_override_honoured(self, subscription):
        fund(subscription.user, "100")
        SubscriptionDelivery.objects.create(
            subscription=subscription,
            date=MONDAY,
            quantity=2,
            status=SubscriptionDelivery.Status.SKIPPED,
        )
        delivery = services.generate_for_subscription(subscription, MONDAY)
        assert delivery.status == SubscriptionDelivery.Status.SKIPPED
        assert not Order.objects.exists()

    def test_quantity_override_honoured(self, subscription):
        fund(subscription.user, "100")
        SubscriptionDelivery.objects.create(
            subscription=subscription,
            date=MONDAY,
            quantity=1,
            status=SubscriptionDelivery.Status.SCHEDULED,
        )
        delivery = services.generate_for_subscription(subscription, MONDAY)
        assert delivery.is_generated
        # 1 x 30 = 30 + 5% = 31.50
        assert delivery.amount == Decimal("31.50")

    def test_generate_for_date_counts(self, subscription):
        fund(subscription.user, "100")
        counts = services.generate_for_date(MONDAY)
        assert counts["generated"] == 1


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestReporting:
    def test_calendar_marks_upcoming_and_generated(self, subscription):
        fund(subscription.user, "100")
        services.generate_for_subscription(subscription, MONDAY)
        days = services.calendar(subscription, MONDAY.year, MONDAY.month)
        by_date = {d["date"]: d for d in days}
        assert by_date[MONDAY.isoformat()]["status"] == "scheduled"

    def test_monthly_summary(self, subscription):
        fund(subscription.user, "100")
        services.generate_for_subscription(subscription, MONDAY)
        summary = services.monthly_summary(subscription.user, MONDAY.year, MONDAY.month)
        assert summary["deliveries"] == 1
        assert summary["amount_spent"] == "63.00"


@pytest.mark.django_db
class TestLowBalanceTask:
    def test_reminder_when_below_two_days(self, subscription):
        fund(subscription.user, "50")  # daily cost 60 -> threshold 120
        result = send_low_balance_reminders()
        assert result["reminders_sent"] == 1

    def test_no_reminder_when_funded(self, subscription):
        fund(subscription.user, "500")
        result = send_low_balance_reminders()
        assert result["reminders_sent"] == 0


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestSubscriptionAPI:
    def test_create(self, auth_client, variant, address):
        response = auth_client.post(
            reverse("subscription-list"),
            {
                "variant_id": variant.id,
                "address_id": address.id,
                "quantity": 2,
                "frequency": "daily",
                "start_date": MONDAY.isoformat(),
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["status"] == "active"
        assert response.data["daily_cost"] == "60.00"

    def test_create_custom_requires_dates(self, auth_client, variant, address):
        response = auth_client.post(
            reverse("subscription-list"),
            {
                "variant_id": variant.id,
                "address_id": address.id,
                "frequency": "custom",
                "custom_days": [],
                "start_date": MONDAY.isoformat(),
            },
            format="json",
        )
        assert response.status_code == 400
        assert "custom_days" in response.data["errors"]

    def test_cannot_use_other_users_address(self, auth_client, variant, db):
        other = User.objects.create_user(phone="+919999999999", name="Other")
        other_address = Address.objects.create(
            user=other, address_line="x", city="y", state="z", pincode="000000"
        )
        response = auth_client.post(
            reverse("subscription-list"),
            {
                "variant_id": variant.id,
                "address_id": other_address.id,
                "frequency": "daily",
                "start_date": MONDAY.isoformat(),
            },
            format="json",
        )
        assert response.status_code == 400

    def test_list_only_own(self, auth_client, subscription):
        response = auth_client.get(reverse("subscription-list"))
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_pause_resume(self, auth_client, subscription):
        paused = auth_client.post(reverse("subscription-pause", args=[subscription.id]))
        assert paused.data["status"] == "paused"
        resumed = auth_client.post(reverse("subscription-resume", args=[subscription.id]))
        assert resumed.data["status"] == "active"

    def test_cancel_is_soft(self, auth_client, subscription):
        response = auth_client.delete(reverse("subscription-detail", args=[subscription.id]))
        assert response.status_code == 204
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.CANCELLED

    def test_skip_future_date(self, auth_client, subscription):
        future = datetime.date.today() + datetime.timedelta(days=3)
        response = auth_client.post(
            reverse("subscription-skip", args=[subscription.id]),
            {"date": future.isoformat()},
            format="json",
        )
        assert response.status_code == 200
        assert subscription.deliveries.filter(
            date=future, status=SubscriptionDelivery.Status.SKIPPED
        ).exists()

    def test_skip_past_cutoff_rejected(self, auth_client, subscription):
        response = auth_client.post(
            reverse("subscription-skip", args=[subscription.id]),
            {"date": datetime.date.today().isoformat()},
            format="json",
        )
        assert response.status_code == 400

    def test_set_quantity_future(self, auth_client, subscription):
        future = datetime.date.today() + datetime.timedelta(days=3)
        response = auth_client.post(
            reverse("subscription-quantity", args=[subscription.id]),
            {"date": future.isoformat(), "quantity": 5},
            format="json",
        )
        assert response.status_code == 200
        assert subscription.deliveries.get(date=future).quantity == 5

    def test_vacation_create_and_delete(self, auth_client, subscription):
        future = datetime.date.today() + datetime.timedelta(days=3)
        created = auth_client.post(
            reverse("subscription-vacation", args=[subscription.id]),
            {"start_date": future.isoformat(), "end_date": (future + datetime.timedelta(days=2)).isoformat()},
            format="json",
        )
        assert created.status_code == 201
        vacation_id = created.data["id"]
        deleted = auth_client.delete(
            reverse("subscription-vacation-delete", args=[subscription.id, vacation_id])
        )
        assert deleted.status_code == 204

    def test_calendar(self, auth_client, subscription):
        response = auth_client.get(
            reverse("subscription-calendar", args=[subscription.id]),
            {"month": f"{MONDAY.year:04d}-{MONDAY.month:02d}"},
        )
        assert response.status_code == 200
        assert "days" in response.data

    def test_summary(self, auth_client, subscription):
        response = auth_client.get(
            reverse("subscription-summary"),
            {"month": f"{MONDAY.year:04d}-{MONDAY.month:02d}"},
        )
        assert response.status_code == 200
        assert "amount_spent" in response.data

    def test_requires_auth(self):
        client = APIClient()
        response = client.get(reverse("subscription-list"))
        assert response.status_code == 401
