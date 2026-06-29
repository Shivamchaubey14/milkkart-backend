import datetime
import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .models import DeliveryAssignment, DeliveryPartner

logger = logging.getLogger(__name__)

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

    assignment = DeliveryAssignment.objects.create(order=order, rider=rider)
    _notify_rider_assigned(assignment)
    return assignment


def _notify_rider_assigned(assignment):
    """Alert the rider that a new order was assigned — records an in-app
    notification and fires a push (banner + sound + vibration on the device).
    Best-effort: a notification failure must never block the assignment."""
    try:
        from apps.notifications.models import Category
        from apps.notifications.services import notify

        order = assignment.order
        short = str(order.order_number)[:8]
        address = (order.address_snapshot or "").strip().replace("\n", ", ")
        notify(
            assignment.rider.user,
            Category.ORDER,
            "New delivery assigned 🛵",
            f"Order #{short} — {address[:90]}" if address else f"Order #{short} is ready for pickup.",
            data={"type": "new_assignment", "order_number": str(order.order_number)},
            channels=("push",),
        )
    except Exception:
        logger.exception("Failed to notify rider of new assignment %s", getattr(assignment, "id", "?"))


# Relations needed to build a delivery payload without per-row N+1 queries.
_DELIVERY_PREFETCH = (
    "order__subscription_deliveries",
    "order__items__variant__product",
    "order__items__variant__product__images",
)


def _delivery_payload(a, request=None):
    """Serialize one assignment into the delivery shape the rider app consumes —
    customer, address, money, items (with resolved images) and the date it counts
    against (delivered_at for finished deliveries, else when it was assigned)."""
    from apps.catalog.serializers import resolve_image_url
    from apps.payments.models import Payment

    order = a.order
    try:
        payment = order.payment
        is_cod = payment.method == Payment.Method.COD
        payment_method = payment.method
        payment_label = payment.get_method_display()
    except Payment.DoesNotExist:
        is_cod = False
        payment_method = ""
        payment_label = ""
    cod_amount = order.total if is_cod else Decimal("0")
    is_subscription = len(order.subscription_deliveries.all()) > 0
    items = list(order.items.all())
    addr = getattr(order, "address", None)
    dest_lat = str(addr.latitude) if addr and addr.latitude is not None else None
    dest_lng = str(addr.longitude) if addr and addr.longitude is not None else None

    def product_image(it):
        product = it.variant.product if it.variant and it.variant.product else None
        return resolve_image_url(product, request) if product else ""

    customer = order.user
    when = a.delivered_at or a.assigned_at
    when_local = timezone.localtime(when) if when else None
    return {
        "order_number": str(order.order_number),
        "address": order.address_snapshot,
        "customer_name": (customer.name or "").strip() if customer else "",
        "customer_phone": customer.phone if customer else "",
        "customer_avatar": customer.avatar if customer else "",
        "dest_lat": dest_lat,
        "dest_lng": dest_lng,
        "total": str(order.total),
        "status": a.status,
        "type": "subscription" if is_subscription else "instant",
        # instant vs next-day pre-order, and the scheduled delivery date (if any)
        "delivery_type": order.delivery_type,
        "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
        "is_cod": is_cod,
        "payment_method": payment_method,
        "payment_label": payment_label,
        "cod_amount": str(cod_amount),
        "item_count": len(items),
        "item_images": [product_image(it) for it in items[:4]],
        "items": [
            {
                "id": it.id,
                "product_name": it.product_name,
                "variant_label": it.variant_label,
                "quantity": it.quantity,
                "is_returned": it.is_returned,
                "image_url": product_image(it),
            }
            for it in items
        ],
        "date": when_local.date().isoformat() if when_local else None,
        "at": when_local.isoformat() if when_local else None,
    }


def _item_image(it, request=None):
    from apps.catalog.serializers import resolve_image_url

    product = it.variant.product if it.variant and it.variant.product else None
    return resolve_image_url(product, request) if product else ""


def rider_earnings_summary(rider, request=None, anchor=None, days=14, top=8):
    """Earnings breakdown for the rider Earnings screen.

    A rider earns a flat fee per delivered order (no per-product rate), so for the
    "by product" view we attribute each order's fee across its delivered items in
    proportion to quantity.

    ``anchor`` is the day the user is inspecting (defaults to today). The headline
    totals are all-time; ``daily`` is the ``days``-day window ending at ``anchor``
    (for the chart), while ``selected`` and ``by_product`` are scoped to ``anchor``
    so the picker shows that single day's earnings and which products drove them.
    """
    import datetime as _dt
    from collections import OrderedDict

    fee = Decimal(settings.DELIVERY_RIDER_FEE)
    cent = Decimal("0.01")
    anchor = anchor or timezone.localdate()
    anchor_iso = anchor.isoformat()

    delivered = (
        DeliveryAssignment.objects.filter(rider=rider, status=DeliveryAssignment.Status.DELIVERED)
        .select_related("order")
        .prefetch_related(
            "order__items__variant__product",
            "order__items__variant__product__images",
        )
    )

    # Seed the `days`-day window ending at the anchor so the chart has a
    # continuous x-axis even on days with no deliveries.
    counts = OrderedDict()
    for i in range(days - 1, -1, -1):
        counts[(anchor - _dt.timedelta(days=i)).isoformat()] = 0

    product_acc = {}  # name -> {qty, deliveries, earnings, image_url} — anchor day only
    total_deliveries = 0
    selected_deliveries = 0

    for a in delivered:
        total_deliveries += 1
        day = timezone.localtime(a.delivered_at).date().isoformat() if a.delivered_at else None
        if day in counts:
            counts[day] += 1
        if day != anchor_iso:
            continue

        selected_deliveries += 1
        items = [it for it in a.order.items.all() if not it.is_returned]
        total_qty = sum(it.quantity for it in items)
        for it in items:
            acc = product_acc.setdefault(
                it.product_name,
                {
                    "product_name": it.product_name,
                    "qty": 0,
                    "deliveries": 0,
                    "earnings": Decimal("0"),
                    "image_url": _item_image(it, request),
                },
            )
            acc["qty"] += it.quantity
            if total_qty:
                acc["earnings"] += fee * it.quantity / total_qty
        for name in {it.product_name for it in items}:
            product_acc[name]["deliveries"] += 1

    by_product = sorted(product_acc.values(), key=lambda v: v["earnings"], reverse=True)[:top]

    return {
        "fee_per_delivery": str(fee),
        "total_earnings": str((fee * total_deliveries).quantize(cent, rounding=ROUND_HALF_UP)),
        "total_deliveries": total_deliveries,
        "date": anchor_iso,
        "selected": {
            "date": anchor_iso,
            "deliveries": selected_deliveries,
            "earnings": str((fee * selected_deliveries).quantize(cent, rounding=ROUND_HALF_UP)),
        },
        "daily": [
            {"date": day, "deliveries": n, "earnings": str((fee * n).quantize(cent, rounding=ROUND_HALF_UP))}
            for day, n in counts.items()
        ],
        "by_product": [
            {
                "product_name": acc["product_name"],
                "image_url": acc["image_url"],
                "qty": acc["qty"],
                "deliveries": acc["deliveries"],
                "earnings": str(acc["earnings"].quantize(cent, rounding=ROUND_HALF_UP)),
            }
            for acc in by_product
        ],
    }


def rider_deliveries_list(rider, kind, request=None):
    """A rider's deliveries of one ``kind`` across all dates, newest first, for the
    history screens reached from the Delivered/Pending/Returned stat cards.

    ``kind`` is one of: ``delivered``, ``returned`` (terminal, grouped by the day
    they finished) or ``pending`` (still-active, grouped by when assigned).
    """
    if kind == "delivered":
        statuses, order_by = [DeliveryAssignment.Status.DELIVERED], "-delivered_at"
    elif kind == "returned":
        statuses, order_by = [DeliveryAssignment.Status.RETURNED], "-delivered_at"
    else:
        statuses, order_by = list(ACTIVE_STATUSES), "-assigned_at"

    assignments = (
        DeliveryAssignment.objects.filter(rider=rider, status__in=statuses)
        .select_related("order", "order__user")
        .prefetch_related(*_DELIVERY_PREFETCH)
        .order_by(order_by)
    )
    return {"kind": kind, "deliveries": [_delivery_payload(a, request) for a in assignments]}


def rider_day_summary(rider, date, request=None):
    """A rider's daily delivery list, COD collection summary and earnings (FR-DEL-03).

    Includes assignments worked on ``date`` (assigned or delivered that day) plus
    any still-active ones, distinguishing subscription deliveries from instant
    orders and totalling cash-on-delivery to collect vs. already collected.

    ``request`` is used to resolve product image URLs to absolute URLs the app can
    load (same as the catalog/orders endpoints).
    """
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
        .select_related("order", "order__user")
        .prefetch_related(*_DELIVERY_PREFETCH)
        .distinct()
    )

    fee = Decimal(settings.DELIVERY_RIDER_FEE)
    deliveries, delivered, pending, returned = [], 0, 0, 0
    cod_to_collect, cod_collected, cod_collected_upi = Decimal("0"), Decimal("0"), Decimal("0")

    for a in assignments:
        payload = _delivery_payload(a, request)
        deliveries.append(payload)
        is_cod = payload["is_cod"]
        cod_amount = Decimal(payload["cod_amount"])

        if a.status == DeliveryAssignment.Status.DELIVERED:
            delivered += 1
            cod_collected += cod_amount
            if is_cod and a.cod_paid_via_upi:
                cod_collected_upi += cod_amount
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
            "cod_collected_upi": str(cod_collected_upi),
            "cod_collected_cash": str(cod_collected - cod_collected_upi),
        },
        "deliveries": deliveries,
    }
