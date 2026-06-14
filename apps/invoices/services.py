"""Invoice generation, emailing and monthly statements.

Invoices snapshot an order's totals; the e-mail goes out through the
notifications email channel (a mock backend in dev — swap for SES in prod).
"""

import logging
from decimal import Decimal

from django.utils import timezone

from .models import Invoice

logger = logging.getLogger(__name__)


def generate_invoice(order):
    """Return the order's invoice, creating it (totals snapshotted) if absent.

    Idempotent: an order never gets a second invoice.
    """
    existing = Invoice.objects.filter(order=order).first()
    if existing:
        return existing
    return Invoice.objects.create(
        order=order,
        subtotal=order.subtotal,
        discount=order.discount,
        delivery_fee=order.delivery_fee,
        small_cart_fee=order.small_cart_fee,
        tax=order.tax,
        total=order.total,
    )


def email_invoice(invoice):
    """E-mail the invoice to the customer and stamp ``emailed_at``.

    Routes through the notifications dispatcher so it is recorded in-app and
    respects the user's channel preferences. Best-effort: a notification failure
    never raises to the caller.
    """
    order = invoice.order
    title = f"Invoice {invoice.number}"
    body = (
        f"Your invoice {invoice.number} for order {order.order_number} "
        f"(₹{invoice.total}) is ready."
    )
    data = {
        "invoice_number": invoice.number,
        "order_number": str(order.order_number),
        "total": str(invoice.total),
    }
    try:
        from apps.notifications.models import Category
        from apps.notifications.services import notify

        notify(order.user, Category.ORDER, title, body, data=data, channels=("email",))
    except Exception:
        logger.exception("Invoice e-mail failed for invoice %s", invoice.pk)

    invoice.emailed_at = timezone.now()
    invoice.save(update_fields=["emailed_at"])
    return invoice


def build_statement(user, year, month):
    """Monthly billing statement: invoice totals plus the subscription summary."""
    invoices = Invoice.objects.filter(
        order__user=user, issued_at__year=year, issued_at__month=month
    )
    total_billed = sum((inv.total for inv in invoices), Decimal("0"))

    subscription_summary = None
    try:
        from apps.subscriptions.services import monthly_summary

        subscription_summary = monthly_summary(user, year, month)
    except Exception:
        logger.exception("Subscription summary failed for statement %s-%s", year, month)

    return {
        "year": year,
        "month": month,
        "invoice_count": invoices.count(),
        "total_billed": str(total_billed),
        "subscription_summary": subscription_summary,
    }
