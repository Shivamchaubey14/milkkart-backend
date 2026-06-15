"""Celery tasks for invoices."""

import logging

from celery import shared_task

from .models import Invoice
from .services import email_invoice, generate_invoice

logger = logging.getLogger(__name__)


@shared_task
def generate_and_email_invoice(order_id):
    """Generate an order's invoice (if needed) and e-mail it to the customer."""
    from apps.orders.models import Order

    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning("generate_and_email_invoice: order %s not found", order_id)
        return None

    invoice = generate_invoice(order)
    email_invoice(invoice)
    return invoice.number


@shared_task
def email_invoice_task(invoice_id):
    """E-mail an already-generated invoice."""
    try:
        invoice = Invoice.objects.get(pk=invoice_id)
    except Invoice.DoesNotExist:
        logger.warning("email_invoice_task: invoice %s not found", invoice_id)
        return None
    email_invoice(invoice)
    return invoice.number
