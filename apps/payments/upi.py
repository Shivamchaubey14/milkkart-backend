"""Gateway-agnostic UPI intent/QR construction.

A UPI "intent" URL (NPCI spec) encodes a collect request to the merchant's
virtual payment address (VPA). Any UPI app — Google Pay, PhonePe, Paytm, a bank
app — can open the URL (mobile) or scan it as a QR (web/desktop) and pay, with no
dependency on a specific payment gateway.

``tr`` (transaction reference) carries our gateway order id, so the same value
reconciles the payment whether it arrives via a gateway webhook or manual review.
"""

from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings


def build_upi_uri(amount, ref, note="MilkKart wallet top-up"):
    """Return a ``upi://pay?...`` URI for ``amount`` rupees to the merchant VPA.

    The same string is used as the deep link (mobile) and the QR payload (web).
    """
    params = {
        "pa": settings.UPI_VPA,
        "pn": settings.UPI_PAYEE_NAME,
        "am": f"{Decimal(amount):.2f}",
        "cu": "INR",
        "tn": note,
    }
    # The merchant-style transaction reference (tr) can trip UPI's risk engine
    # when collecting to a *personal* VPA. Omit it for a plain P2P-style intent.
    if not getattr(settings, "UPI_INTENT_OMIT_REF", False):
        params["tr"] = str(ref)
    return "upi://pay?" + urlencode(params)


def upi_payload(amount, ref, note="MilkKart wallet top-up"):
    """The client-facing UPI block: the intent/QR string plus display fields."""
    return {
        "intent": build_upi_uri(amount, ref, note),
        "vpa": settings.UPI_VPA,
        "payee_name": settings.UPI_PAYEE_NAME,
    }
