"""Celery tasks for subscriptions.

``generate_subscription_orders`` runs nightly after the 10 PM cutoff and builds
the next morning's orders. ``send_low_balance_reminders`` warns customers whose
wallet won't cover the next two days of subscriptions.
"""

import datetime
import logging
from collections import defaultdict
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from apps.wallet.models import get_or_create_wallet

from .models import Subscription
from .services import generate_for_date

logger = logging.getLogger(__name__)


@shared_task
def generate_subscription_orders(target_date=None):
    """Generate next-day subscription orders and auto-debit wallets.

    Runs after the cutoff, so the schedule (skips, vacations, quantity changes) is
    settled. ``target_date`` (ISO string) is accepted for manual replays; defaults
    to tomorrow.
    """
    if target_date:
        date = datetime.date.fromisoformat(target_date)
    else:
        date = timezone.localdate() + datetime.timedelta(days=1)

    counts = generate_for_date(date)
    return {"date": date.isoformat(), **counts}


@shared_task
def send_low_balance_reminders():
    """Notify customers whose wallet balance is below two days of subscription cost."""
    from apps.notifications.models import Category
    from apps.notifications.services import notify

    daily_cost = defaultdict(Decimal)
    active = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE
    ).select_related("variant", "user")
    for subscription in active:
        daily_cost[subscription.user] += subscription.daily_cost

    notified = 0
    for user, cost in daily_cost.items():
        if cost <= 0:
            continue
        wallet = get_or_create_wallet(user)
        threshold = cost * 2
        if wallet.balance < threshold:
            notify(
                user,
                Category.SUBSCRIPTION,
                "Low wallet balance",
                f"Your wallet balance (₹{wallet.balance}) won't cover your next two days of "
                f"subscriptions (₹{threshold}). Top up to avoid missed deliveries.",
                data={"balance": str(wallet.balance), "threshold": str(threshold)},
                channels=("push", "sms"),
            )
            notified += 1

    return {"reminders_sent": notified}
