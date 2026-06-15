"""Payment gateway abstraction.

Two interchangeable backends sit behind one interface, selected by
``settings.PAYMENT_GATEWAY`` ("mock" by default, "razorpay" in production):

* **mock** — Razorpay-shaped order creation and HMAC signature verification, with
  no external calls. Keeps dev and tests hermetic.
* **razorpay** — the real Razorpay SDK (imported lazily so the dependency is only
  needed when actually enabled).

The view/task layer only depends on the module-level functions below.
"""

import hashlib
import hmac
import uuid

from django.conf import settings


def _backend():
    return getattr(settings, "PAYMENT_GATEWAY", "mock")


def provider():
    """The active gateway backend name ("mock" or "razorpay")."""
    return _backend()


# --------------------------------------------------------------------------- #
# Public interface
# --------------------------------------------------------------------------- #
def create_gateway_order(amount, receipt):
    """Create a gateway order. ``amount`` is a Decimal in rupees (gateways use paise)."""
    if _backend() == "razorpay":
        return _razorpay_create_order(amount, receipt)
    return _mock_create_order(amount, receipt)


def verify_signature(gateway_order_id, gateway_payment_id, signature):
    """Verify a checkout callback signature (order_id|payment_id)."""
    if _backend() == "razorpay":
        return _razorpay_verify_signature(gateway_order_id, gateway_payment_id, signature)
    return _mock_verify_signature(gateway_order_id, gateway_payment_id, signature)


def refund_payment(gateway_payment_id, amount):
    """Issue a refund. ``amount`` is a Decimal in rupees."""
    if _backend() == "razorpay":
        return _razorpay_refund(gateway_payment_id, amount)
    return _mock_refund(gateway_payment_id, amount)


def verify_webhook_signature(raw_body, signature):
    """Verify a webhook payload signature: HMAC-SHA256(body, webhook_secret).

    Razorpay signs the raw request body with the webhook secret (distinct from the
    checkout key secret). The mock backend uses the same scheme so webhooks are
    testable end to end.
    """
    secret = settings.PAYMENT_WEBHOOK_SECRET.encode()
    body = raw_body if isinstance(raw_body, (bytes, bytearray)) else raw_body.encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# --------------------------------------------------------------------------- #
# Mock backend
# --------------------------------------------------------------------------- #
def _mock_create_order(amount, receipt):
    return {
        "id": f"order_{uuid.uuid4().hex[:14]}",
        "amount": int(amount * 100),
        "currency": "INR",
        "receipt": str(receipt),
        "key_id": settings.PAYMENT_GATEWAY_KEY_ID,
    }


def sign(gateway_order_id, gateway_payment_id):
    """HMAC-SHA256 signature for an order/payment pair (mock backend / tests)."""
    return hmac.new(
        settings.PAYMENT_GATEWAY_SECRET.encode(),
        f"{gateway_order_id}|{gateway_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _mock_verify_signature(gateway_order_id, gateway_payment_id, signature):
    expected = sign(gateway_order_id, gateway_payment_id)
    return hmac.compare_digest(expected, signature or "")


def _mock_refund(gateway_payment_id, amount):
    return {
        "id": f"rfnd_{uuid.uuid4().hex[:14]}",
        "payment_id": gateway_payment_id,
        "amount": int(amount * 100),
        "currency": "INR",
        "status": "processed",
    }


# --------------------------------------------------------------------------- #
# Razorpay backend (real SDK, imported lazily)
# --------------------------------------------------------------------------- #
def _razorpay_client():
    import razorpay

    return razorpay.Client(
        auth=(settings.PAYMENT_GATEWAY_KEY_ID, settings.PAYMENT_GATEWAY_SECRET)
    )


def _razorpay_create_order(amount, receipt):
    order = _razorpay_client().order.create(
        {"amount": int(amount * 100), "currency": "INR", "receipt": str(receipt)}
    )
    return {
        "id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "receipt": str(receipt),
        "key_id": settings.PAYMENT_GATEWAY_KEY_ID,
    }


def _razorpay_verify_signature(gateway_order_id, gateway_payment_id, signature):
    try:
        _razorpay_client().utility.verify_payment_signature(
            {
                "razorpay_order_id": gateway_order_id,
                "razorpay_payment_id": gateway_payment_id,
                "razorpay_signature": signature,
            }
        )
        return True
    except Exception:
        return False


def _razorpay_refund(gateway_payment_id, amount):
    refund = _razorpay_client().payment.refund(
        gateway_payment_id, {"amount": int(amount * 100)}
    )
    return {
        "id": refund["id"],
        "payment_id": gateway_payment_id,
        "amount": refund["amount"],
        "currency": "INR",
        "status": refund.get("status", "processed"),
    }
