"""Stock-movement engine: the single path through which variant stock changes.

Every adjustment is atomic, row-locked, and recorded in the StockMovement ledger.
Crossing the low-stock threshold downward alerts ops/warehouse staff.
"""

import logging

from django.conf import settings
from django.db import transaction

from .models import StockMovement

logger = logging.getLogger(__name__)


class OutOfStock(Exception):
    """Raised when a negative adjustment would drive stock below zero."""


def adjust_stock(variant, delta, reason, *, note="", user=None, order=None, lock=True):
    """Apply a signed ``delta`` to ``variant`` stock and record a movement.

    ``lock`` re-selects the row ``FOR UPDATE``; pass ``lock=False`` when the caller
    already holds the lock in the surrounding transaction. Raises :class:`OutOfStock`
    if the result would be negative. Returns the created :class:`StockMovement`.
    """
    from apps.catalog.models import ProductVariant

    with transaction.atomic():
        if lock:
            locked = ProductVariant.objects.select_for_update().get(pk=variant.pk)
        else:
            locked = variant
        previous = locked.stock
        new_stock = previous + delta
        if new_stock < 0:
            raise OutOfStock(f"{locked.sku}: cannot reduce {previous} by {-delta}.")

        locked.stock = new_stock
        locked.save(update_fields=["stock"])
        movement = StockMovement.objects.create(
            variant=locked,
            delta=delta,
            reason=reason,
            balance_after=new_stock,
            note=note,
            order=order,
            created_by=user,
        )
        variant.stock = new_stock  # keep the caller's instance consistent

    threshold = getattr(settings, "LOW_STOCK_THRESHOLD", 10)
    if delta < 0 and previous > threshold >= new_stock:
        _low_stock_alert(locked, new_stock)
    return movement


def restock(variant, quantity, *, user=None, note=""):
    """Convenience wrapper for a positive RESTOCK movement."""
    if quantity <= 0:
        raise ValueError("Restock quantity must be positive.")
    return adjust_stock(
        variant, quantity, StockMovement.Reason.RESTOCK, note=note, user=user
    )


def low_stock_variants(threshold=None):
    """Active variants at or below the low-stock threshold."""
    from apps.catalog.models import ProductVariant

    if threshold is None:
        threshold = getattr(settings, "LOW_STOCK_THRESHOLD", 10)
    return (
        ProductVariant.objects.filter(is_active=True, stock__lte=threshold)
        .select_related("product")
        .order_by("stock")
    )


# --------------------------------------------------------------------------- #
# Low-stock alerting (best-effort)
# --------------------------------------------------------------------------- #
def _low_stock_alert(variant, stock):
    try:
        from django.contrib.auth import get_user_model

        from apps.notifications.models import Category
        from apps.notifications.services import notify

        User = get_user_model()
        staff = User.objects.filter(
            role__in=(User.Role.OPS, User.Role.WAREHOUSE, User.Role.ADMIN)
        )
        title = "Low stock"
        body = f"{variant.product.name} ({variant.label}) is down to {stock} units."
        data = {"variant_id": variant.pk, "sku": variant.sku, "stock": stock}
        for member in staff:
            notify(member, Category.SYSTEM, title, body, data=data)
    except Exception:
        logger.exception("Low-stock alert failed for variant %s", getattr(variant, "pk", None))
