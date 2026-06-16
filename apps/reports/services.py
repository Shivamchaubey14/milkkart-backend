"""Read-only analytics aggregations for back-office reporting.

All figures are computed with ORM aggregation over a ``[start, end]`` date range
(inclusive). Revenue excludes cancelled orders.

Date filtering compares the timestamp columns directly against an aware
``[start 00:00, end+1day 00:00)`` window rather than using ``__date`` lookups —
the latter emit MySQL ``CONVERT_TZ`` and silently match nothing unless the
server's timezone tables are loaded.
"""

import datetime
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count, DecimalField, F, Q, Sum
from django.utils import timezone


def _money(value):
    return str((value or Decimal("0")).quantize(Decimal("0.01")))


def _bounds(start, end):
    """Return aware [start 00:00, end+1day 00:00) datetimes for the active TZ."""
    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min)
    if settings.USE_TZ:
        start_dt = timezone.make_aware(start_dt)
        end_dt = timezone.make_aware(end_dt)
    return start_dt, end_dt


def sales_summary(start, end):
    from apps.orders.models import Order

    start_dt, end_dt = _bounds(start, end)
    qs = Order.objects.filter(
        placed_at__gte=start_dt, placed_at__lt=end_dt
    ).exclude(status=Order.Status.CANCELLED)
    agg = qs.aggregate(revenue=Sum("total"), orders=Count("id"))
    revenue = agg["revenue"] or Decimal("0")
    orders = agg["orders"] or 0
    aov = revenue / orders if orders else Decimal("0")
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "orders": orders,
        "revenue": _money(revenue),
        "average_order_value": _money(aov),
    }


def top_products(start, end, limit=10):
    from apps.orders.models import Order, OrderItem

    start_dt, end_dt = _bounds(start, end)
    rows = (
        OrderItem.objects.filter(
            order__placed_at__gte=start_dt, order__placed_at__lt=end_dt
        )
        .exclude(order__status=Order.Status.CANCELLED)
        .values("product_name")
        .annotate(
            units=Sum("quantity"),
            revenue=Sum(
                F("product_price") * F("quantity"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
        .order_by("-units")[:limit]
    )
    return [
        {"product_name": r["product_name"], "quantity": r["units"], "revenue": _money(r["revenue"])}
        for r in rows
    ]


def order_status_breakdown(start, end):
    from apps.orders.models import Order

    start_dt, end_dt = _bounds(start, end)
    rows = (
        Order.objects.filter(placed_at__gte=start_dt, placed_at__lt=end_dt)
        .values("status")
        .annotate(count=Count("id"))
    )
    return {row["status"]: row["count"] for row in rows}


def subscription_report(start, end):
    """Current subscription mix plus new/cancelled counts within the period.

    Cancellations are approximated by ``updated_at`` (subscriptions carry no
    dedicated cancelled-at timestamp).
    """
    from apps.subscriptions.models import Subscription

    by_status = {
        row["status"]: row["count"]
        for row in Subscription.objects.values("status").annotate(count=Count("id"))
    }
    start_dt, end_dt = _bounds(start, end)
    new_in_period = Subscription.objects.filter(
        created_at__gte=start_dt, created_at__lt=end_dt
    ).count()
    cancelled_in_period = Subscription.objects.filter(
        status=Subscription.Status.CANCELLED,
        updated_at__gte=start_dt,
        updated_at__lt=end_dt,
    ).count()
    return {
        "active": by_status.get(Subscription.Status.ACTIVE, 0),
        "paused": by_status.get(Subscription.Status.PAUSED, 0),
        "cancelled": by_status.get(Subscription.Status.CANCELLED, 0),
        "total": sum(by_status.values()),
        "new_in_period": new_in_period,
        "cancelled_in_period": cancelled_in_period,
    }


def rider_performance(start, end):
    from apps.delivery.models import DeliveryAssignment
    from apps.support.models import OrderReview

    start_dt, end_dt = _bounds(start, end)
    rows = (
        DeliveryAssignment.objects.filter(
            assigned_at__gte=start_dt, assigned_at__lt=end_dt
        )
        .values("rider__user__phone")
        .annotate(
            assignments=Count("id"),
            delivered=Count("id", filter=Q(status=DeliveryAssignment.Status.DELIVERED)),
        )
        .order_by("-delivered")
    )

    ratings = {
        r["order__assignment__rider__user__phone"]: r["avg"]
        for r in OrderReview.objects.filter(rider_rating__isnull=False)
        .values("order__assignment__rider__user__phone")
        .annotate(avg=Avg("rider_rating"))
    }

    return [
        {
            "rider": row["rider__user__phone"],
            "assignments": row["assignments"],
            "delivered": row["delivered"],
            "avg_rider_rating": (
                round(ratings[row["rider__user__phone"]], 2)
                if ratings.get(row["rider__user__phone"]) is not None
                else None
            ),
        }
        for row in rows
    ]
