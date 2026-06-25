import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .models import DeliveryAssignment, DeliveryPartner

ACTIVE_STATUSES = [
    DeliveryAssignment.Status.ASSIGNED,
    DeliveryAssignment.Status.ACCEPTED,
    DeliveryAssignment.Status.PICKED_UP,
]


class NoRiderAvailable(Exception):
    """Raised when no on-duty rider is available for auto-assignment."""


def available_riders():
    return DeliveryPartner.objects.filter(is_active=True, is_on_duty=True)


def riders_with_load(active_only=True):
    """Delivery partners annotated with their current open-assignment ``load``,
    ordered on-duty first then least-loaded — for the ops assignment picker."""
    qs = DeliveryPartner.objects.select_related("user").annotate(
        load=Count("assignments", filter=Q(assignments__status__in=ACTIVE_STATUSES))
    )
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("-is_on_duty", "load", "id")


def assign_order(order, rider=None):
    """Assign an order to a rider. Auto-picks the least-loaded on-duty rider if none given."""
    existing = DeliveryAssignment.objects.filter(order=order).first()
    if existing and existing.is_active:
        return existing

    if rider is None:
        rider = (
            available_riders()
            .annotate(active_load=Count("assignments", filter=Q(assignments__status__in=ACTIVE_STATUSES)))
            .order_by("active_load", "id")
            .first()
        )
        if rider is None:
            raise NoRiderAvailable("No on-duty rider available.")

    return DeliveryAssignment.objects.create(order=order, rider=rider)


def rider_day_summary(rider, date):
    """A rider's daily delivery list, COD collection summary and earnings (FR-DEL-03).

    Includes assignments worked on ``date`` (assigned or delivered that day) plus
    any still-active ones, distinguishing subscription deliveries from instant
    orders and totalling cash-on-delivery to collect vs. already collected.
    """
    from apps.payments.models import Payment

    start = datetime.datetime.combine(date, datetime.time.min)
    end = start + datetime.timedelta(days=1)
    if settings.USE_TZ:
        start, end = timezone.make_aware(start), timezone.make_aware(end)

    assignments = (
        DeliveryAssignment.objects.filter(rider=rider)
        .filter(
            Q(assigned_at__gte=start, assigned_at__lt=end)
            | Q(delivered_at__gte=start, delivered_at__lt=end)
            | Q(status__in=ACTIVE_STATUSES)
        )
        .select_related("order")
        .prefetch_related("order__subscription_deliveries", "order__items__variant__product")
        .distinct()
    )

    fee = Decimal(settings.DELIVERY_RIDER_FEE)
    deliveries, delivered, pending, returned = [], 0, 0, 0
    cod_to_collect, cod_collected = Decimal("0"), Decimal("0")

    for a in assignments:
        order = a.order
        try:
            is_cod = order.payment.method == Payment.Method.COD
        except Payment.DoesNotExist:
            is_cod = False
        cod_amount = order.total if is_cod else Decimal("0")
        is_subscription = len(order.subscription_deliveries.all()) > 0
        items = list(order.items.all())

        deliveries.append({
            "order_number": str(order.order_number),
            "address": order.address_snapshot,
            "total": str(order.total),
            "status": a.status,
            "type": "subscription" if is_subscription else "instant",
            "is_cod": is_cod,
            "cod_amount": str(cod_amount),
            "item_count": len(items),
            "item_images": [
                (it.variant.product.image_url if it.variant and it.variant.product else "")
                for it in items[:4]
            ],
            "items": [
                {
                    "id": it.id,
                    "product_name": it.product_name,
                    "variant_label": it.variant_label,
                    "quantity": it.quantity,
                    "is_returned": it.is_returned,
                    "image_url": (it.variant.product.image_url if it.variant and it.variant.product else ""),
                }
                for it in items
            ],
        })

        if a.status == DeliveryAssignment.Status.DELIVERED:
            delivered += 1
            cod_collected += cod_amount
        elif a.status == DeliveryAssignment.Status.RETURNED:
            # Refused/returned — nothing to collect, tracked on its own.
            returned += 1
        elif a.status != DeliveryAssignment.Status.CANCELLED:
            pending += 1
            cod_to_collect += cod_amount

    earnings = (fee * delivered).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "date": date.isoformat(),
        "stats": {
            "total": len(deliveries),
            "delivered": delivered,
            "pending": pending,
            "returned": returned,
            "earnings": str(earnings),
            "rider_fee": str(fee),
            "cod_to_collect": str(cod_to_collect),
            "cod_collected": str(cod_collected),
        },
        "deliveries": deliveries,
    }
