"""Domain logic for milk subscriptions: schedule calculation, the 10 PM cutoff,
nightly order generation with wallet auto-debit, and reporting helpers."""

import datetime
import logging
from calendar import monthrange
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.wallet.models import InsufficientBalance, get_or_create_wallet

from .models import Subscription, SubscriptionDelivery

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


class OutOfStock(Exception):
    """Raised when a variant lacks the stock to fulfil a day's delivery."""


# --------------------------------------------------------------------------- #
# Schedule calculation
# --------------------------------------------------------------------------- #
def is_due(subscription, date):
    """Whether ``subscription`` should deliver on ``date`` per its frequency.

    Ignores per-day overrides (skips) — those are resolved at generation time —
    but honours status, start date and vacation ranges.
    """
    if subscription.status != Subscription.Status.ACTIVE:
        return False
    if date < subscription.start_date:
        return False

    frequency = subscription.frequency
    if frequency == Subscription.Frequency.DAILY:
        due = True
    elif frequency == Subscription.Frequency.WEEKDAYS:
        due = date.weekday() < 5
    elif frequency == Subscription.Frequency.ALTERNATE:
        due = (date - subscription.start_date).days % 2 == 0
    elif frequency == Subscription.Frequency.CUSTOM:
        due = date.isoformat() in (subscription.custom_days or [])
    else:
        due = False

    if not due:
        return False

    on_vacation = subscription.vacations.filter(
        start_date__lte=date, end_date__gte=date
    ).exists()
    return not on_vacation


# --------------------------------------------------------------------------- #
# Cutoff
# --------------------------------------------------------------------------- #
def cutoff_for(date, now=None):
    """The local datetime by which changes affecting ``date`` must be made.

    Changes for a delivery date must land before the cutoff hour on the prior day
    (default 10 PM), so the nightly generator sees a settled schedule.
    """
    hour = getattr(settings, "SUBSCRIPTION_CUTOFF_HOUR", 22)
    naive = datetime.datetime.combine(
        date - datetime.timedelta(days=1), datetime.time(hour=hour)
    )
    return timezone.make_aware(naive, timezone.get_current_timezone())


def is_change_allowed(date, now=None):
    """True if a customer may still change the delivery on ``date``."""
    now = now or timezone.localtime()
    return now < cutoff_for(date)


# --------------------------------------------------------------------------- #
# Order generation
# --------------------------------------------------------------------------- #
def _address_snapshot(address):
    return (
        f"{address.address_line}, {address.landmark}, "
        f"{address.city}, {address.state} {address.pincode}"
    )


def _quantize(amount):
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def _create_order(subscription, variant, quantity, date):
    """Create a CONFIRMED prepaid order for one day's subscription delivery.

    Subscriptions get free delivery and no small-cart fee; tax mirrors the cart
    bill engine's ``TAX_PERCENT`` for parity. Caller holds the row lock on
    ``variant`` and the surrounding transaction.
    """
    from apps.orders.models import Order, OrderItem

    subtotal = _quantize(variant.price * quantity)
    tax = _quantize(subtotal * settings.TAX_PERCENT / Decimal("100"))
    total = _quantize(subtotal + tax)

    order = Order.objects.create(
        user=subscription.user,
        status=Order.Status.CONFIRMED,
        subtotal=subtotal,
        tax=tax,
        total=total,
        address=subscription.address,
        address_snapshot=_address_snapshot(subscription.address),
        notes=f"Subscription delivery for {date.isoformat()} — {variant.product.name} ({variant.label})",
    )
    OrderItem.objects.create(
        order=order,
        variant=variant,
        product_name=variant.product.name,
        variant_label=variant.label,
        product_price=variant.price,
        quantity=quantity,
    )
    return order, total


def _upsert_delivery(subscription, date, quantity, *, status, amount=Decimal("0"), order=None):
    delivery, _ = SubscriptionDelivery.objects.update_or_create(
        subscription=subscription,
        date=date,
        defaults={
            "quantity": quantity,
            "amount": amount,
            "status": status,
            "order": order,
        },
    )
    return delivery


def generate_for_subscription(subscription, date):
    """Generate (or finalise) one day's delivery for ``subscription`` on ``date``.

    Idempotent: a day already skipped or already generated is left untouched.
    Returns the resulting :class:`SubscriptionDelivery`, or ``None`` when nothing
    was due.
    """
    existing = subscription.deliveries.filter(date=date).first()
    if existing and (existing.status == SubscriptionDelivery.Status.SKIPPED or existing.is_generated):
        return existing

    quantity = existing.quantity if existing else subscription.quantity

    try:
        with transaction.atomic():
            variant = ProductVariant.objects.select_for_update().get(pk=subscription.variant_id)
            if variant.stock < quantity:
                raise OutOfStock()

            order, total = _create_order(subscription, variant, quantity, date)
            variant.stock -= quantity
            variant.save(update_fields=["stock"])

            wallet = get_or_create_wallet(subscription.user)
            wallet.debit(
                total,
                description=f"Subscription delivery {date.isoformat()}",
                order=order,
            )
            delivery = _upsert_delivery(
                subscription,
                date,
                quantity,
                status=SubscriptionDelivery.Status.SCHEDULED,
                amount=total,
                order=order,
            )
    except InsufficientBalance:
        delivery = _upsert_delivery(
            subscription, date, quantity, status=SubscriptionDelivery.Status.FAILED_BALANCE
        )
        _notify(
            subscription.user,
            "Subscription skipped — low balance",
            f"We couldn't deliver your subscription on {date.isoformat()} due to a low wallet "
            "balance. Top up to resume.",
            data={"subscription_id": subscription.pk, "date": date.isoformat()},
            channels=("push", "sms"),
        )
        return delivery
    except OutOfStock:
        delivery = _upsert_delivery(
            subscription, date, quantity, status=SubscriptionDelivery.Status.SKIPPED
        )
        _notify(
            subscription.user,
            "Subscription skipped — out of stock",
            f"Your subscription item was out of stock for {date.isoformat()}; you were not charged.",
            data={"subscription_id": subscription.pk, "date": date.isoformat()},
        )
        return delivery

    _on_generated(delivery)
    return delivery


def _on_generated(delivery):
    """Side effects after a successful generation: assign a rider and notify."""
    try:
        from apps.delivery.services import assign_order

        assign_order(delivery.order)
    except Exception:  # rider assignment is best-effort; never block generation
        logger.exception("Rider assignment failed for order %s", delivery.order_id)

    _notify(
        delivery.subscription.user,
        "Subscription delivery scheduled",
        f"Your subscription will be delivered on {delivery.date.isoformat()}.",
        data={
            "subscription_id": delivery.subscription_id,
            "date": delivery.date.isoformat(),
            "order_number": str(delivery.order.order_number),
        },
    )


def generate_for_date(date):
    """Run generation for every active subscription due on ``date``.

    Returns a summary dict of outcome counts.
    """
    counts = {"generated": 0, "skipped": 0, "failed_balance": 0}
    subscriptions = (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE)
        .select_related("variant__product", "user", "address")
    )
    for subscription in subscriptions:
        if not is_due(subscription, date):
            continue
        delivery = generate_for_subscription(subscription, date)
        if delivery is None:
            continue
        if delivery.status == SubscriptionDelivery.Status.FAILED_BALANCE:
            counts["failed_balance"] += 1
        elif delivery.status == SubscriptionDelivery.Status.SKIPPED:
            counts["skipped"] += 1
        elif delivery.is_generated:
            counts["generated"] += 1
    logger.info("Subscription generation for %s: %s", date, counts)
    return counts


# --------------------------------------------------------------------------- #
# Notifications (thin wrapper so generation degrades gracefully in tests)
# --------------------------------------------------------------------------- #
def _notify(user, title, body, data=None, channels=("push",)):
    try:
        from apps.notifications.models import Category
        from apps.notifications.services import notify

        notify(user, Category.SUBSCRIPTION, title, body, data=data, channels=channels)
    except Exception:
        logger.exception("Subscription notification failed for user %s", getattr(user, "pk", None))


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def calendar(subscription, year, month):
    """Per-day calendar for ``subscription`` in the given month.

    Each entry has the effective status — ``delivered``/``scheduled`` (generated),
    ``skipped``, ``failed_balance`` for recorded days; ``upcoming`` for future due
    days with no record yet — plus the per-day cost.
    """
    from apps.orders.models import Order

    _, days_in_month = monthrange(year, month)
    today = timezone.localdate()
    recorded = {
        d.date: d
        for d in subscription.deliveries.select_related("order").filter(
            date__year=year, date__month=month
        )
    }

    entries = []
    for day in range(1, days_in_month + 1):
        date = datetime.date(year, month, day)
        delivery = recorded.get(date)
        if delivery:
            if delivery.status == SubscriptionDelivery.Status.SCHEDULED and delivery.order:
                effective = (
                    "delivered"
                    if delivery.order.status == Order.Status.DELIVERED
                    else "scheduled"
                )
            else:
                effective = delivery.status
            entries.append(
                {
                    "date": date.isoformat(),
                    "status": effective,
                    "quantity": delivery.quantity,
                    "cost": str(delivery.amount),
                }
            )
        elif is_due(subscription, date) and date >= today:
            entries.append(
                {
                    "date": date.isoformat(),
                    "status": "upcoming",
                    "quantity": subscription.quantity,
                    "cost": str(_quantize(subscription.daily_cost)),
                }
            )
    return entries


def monthly_summary(user, year, month):
    """Aggregate a user's subscription deliveries for a month."""
    deliveries = SubscriptionDelivery.objects.filter(
        subscription__user=user, date__year=year, date__month=month
    )
    delivered = deliveries.filter(order__isnull=False).exclude(
        status=SubscriptionDelivery.Status.SKIPPED
    )
    amount_spent = sum((d.amount for d in delivered), Decimal("0"))
    return {
        "year": year,
        "month": month,
        "deliveries": delivered.count(),
        "skipped": deliveries.filter(status=SubscriptionDelivery.Status.SKIPPED).count(),
        "failed_balance": deliveries.filter(
            status=SubscriptionDelivery.Status.FAILED_BALANCE
        ).count(),
        "amount_spent": str(_quantize(amount_spent)),
    }
