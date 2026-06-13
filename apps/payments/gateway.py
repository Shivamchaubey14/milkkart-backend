"""Mock payment gateway — Razorpay-style order creation and HMAC signature verification.

Swap these functions for the real gateway SDK (Razorpay/Stripe) in production; the
view layer only depends on this module's interface.
"""

import hashlib
import hmac
import uuid

from django.conf import settings


def create_gateway_order(amount, receipt):
    """Create a gateway order and return its handle.

    `amount` is a Decimal in rupees; gateways expect the smallest currency unit (paise).
    """
    return {
        "id": f"order_{uuid.uuid4().hex[:14]}",
        "amount": int(amount * 100),
        "currency": "INR",
        "receipt": str(receipt),
        "key_id": settings.PAYMENT_GATEWAY_KEY_ID,
    }


def sign(gateway_order_id, gateway_payment_id):
    """Compute the expected HMAC-SHA256 signature for an order/payment pair."""
    return hmac.new(
        settings.PAYMENT_GATEWAY_SECRET.encode(),
        f"{gateway_order_id}|{gateway_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(gateway_order_id, gateway_payment_id, signature):
    """Verify a gateway callback signature in constant time."""
    expected = sign(gateway_order_id, gateway_payment_id)
    return hmac.compare_digest(expected, signature or "")
