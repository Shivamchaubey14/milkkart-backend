"""Read-only analytics aggregations for back-office reporting.

All figures are computed with ORM aggregation over a ``[start, end]`` date range
(inclusive). Revenue excludes cancelled orders.
"""

from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, F, Q, Sum


def _money(value):
    return str((value or Decimal("0")).quantize(Decimal("0.01")))


def sales_summary(start, end):
    from apps.orders.models import Order

    qs = Order.objects.filter(
        placed_at__date__gte=start, placed_at__date__lte=end
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

    rows = (
        OrderItem.objects.filter(
            order__placed_at__date__gte=start, order__placed_at__date__lte=end
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

    rows = (
        Order.objects.filter(placed_at__date__gte=start, placed_at__date__lte=end)
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
    new_in_period = Subscription.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end
    ).count()
    cancelled_in_period = Subscription.objects.filter(
        status=Subscription.Status.CANCELLED,
        updated_at__date__gte=start,
        updated_at__date__lte=end,
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

    rows = (
        DeliveryAssignment.objects.filter(
            assigned_at__date__gte=start, assigned_at__date__lte=end
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
