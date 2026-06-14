"""Domain logic for support: product-rating aggregation and ticket resolution.

A ticket is resolved by an agent via a replacement or a wallet refund; refunds
credit the customer's wallet through the same double-entry ledger as everything
else.
"""

import logging

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import ProductRating, SupportTicket

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Product ratings
# --------------------------------------------------------------------------- #
def recalculate_product_rating(product):
    """Recompute and store a product's rating aggregates from its ratings."""
    agg = product.ratings.aggregate(total=Sum("rating"), count=Count("id"))
    product.rating_sum = agg["total"] or 0
    product.rating_count = agg["count"] or 0
    product.save(update_fields=["rating_sum", "rating_count"])


def record_product_rating(
    user, product, rating, *, variant=None, order=None, comment="", photos=None
):
    """Create or update a customer's rating for a product, refreshing aggregates.

    One rating per (user, product, order); re-rating updates the same row so the
    aggregate stays correct.
    """
    obj, _ = ProductRating.objects.update_or_create(
        user=user,
        product=product,
        order=order,
        defaults={
            "rating": rating,
            "variant": variant,
            "comment": comment,
            "photos": photos or [],
        },
    )
    recalculate_product_rating(product)
    return obj


# --------------------------------------------------------------------------- #
# Ticket resolution
# --------------------------------------------------------------------------- #
def resolve_ticket(ticket, *, resolution_type, note="", amount=None):
    """Resolve a ticket via replacement or wallet refund and notify the customer.

    Refunds credit the customer's wallet (REFUND ledger entry). Idempotent: an
    already-resolved ticket is returned untouched.
    """
    if ticket.status == SupportTicket.Status.RESOLVED:
        return ticket

    if resolution_type not in (
        SupportTicket.Resolution.REPLACEMENT,
        SupportTicket.Resolution.REFUND,
    ):
        raise ValueError("resolution_type must be 'replacement' or 'refund'.")

    with transaction.atomic():
        if resolution_type == SupportTicket.Resolution.REFUND:
            if amount is None or amount <= 0:
                raise ValueError("A refund requires a positive amount.")
            from apps.wallet.models import WalletTransaction, get_or_create_wallet

            wallet = get_or_create_wallet(ticket.user)
            wallet.credit(
                amount,
                WalletTransaction.Type.REFUND,
                description=f"Refund for support ticket {ticket.ticket_number}",
                order=ticket.order,
            )
            ticket.refund_amount = amount

        ticket.resolution_type = resolution_type
        ticket.resolution_note = note
        ticket.status = SupportTicket.Status.RESOLVED
        ticket.resolved_at = timezone.now()
        ticket.save(
            update_fields=[
                "resolution_type",
                "resolution_note",
                "refund_amount",
                "status",
                "resolved_at",
                "updated_at",
            ]
        )

    if resolution_type == SupportTicket.Resolution.REFUND:
        body = (
            f"We've resolved your ticket and refunded ₹{amount} to your wallet."
        )
    else:
        body = "We've resolved your ticket and arranged a replacement delivery."
    _notify(
        ticket.user,
        "Support ticket resolved",
        body,
        data={"ticket_number": str(ticket.ticket_number), "resolution": resolution_type},
    )
    return ticket


# --------------------------------------------------------------------------- #
# Notifications (thin wrapper so support degrades gracefully in tests)
# --------------------------------------------------------------------------- #
def _notify(user, title, body, data=None):
    try:
        from apps.notifications.models import Category
        from apps.notifications.services import notify

        notify(user, Category.SYSTEM, title, body, data=data, channels=("push",))
    except Exception:
        logger.exception("Support notification failed for user %s", getattr(user, "pk", None))
