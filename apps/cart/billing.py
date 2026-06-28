"""Cart bill engine — computes the live bill breakdown (FR-CART-02)."""

from decimal import ROUND_HALF_UP, Decimal

from apps.core.models import StoreConfig

TWO_PLACES = Decimal("0.01")


def _q(amount):
    return Decimal(amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def cart_subtotal(cart):
    return sum((i.variant.price * i.quantity for i in cart.items.all()), Decimal("0"))


def compute_bill(cart):
    """Return the full bill breakdown for a cart, honouring any eligible applied coupon."""
    items = list(cart.items.select_related("variant").all())
    subtotal = sum((i.variant.price * i.quantity for i in items), Decimal("0"))
    mrp_total = sum((i.variant.mrp * i.quantity for i in items), Decimal("0"))
    mrp_savings = mrp_total - subtotal

    coupon = cart.applied_coupon
    coupon_discount = Decimal("0")
    coupon_code = None
    if coupon and items:
        eligible, _ = coupon.check_eligibility(cart.user, subtotal)
        if eligible:
            coupon_discount = coupon.calculate_discount(subtotal)
            coupon_code = coupon.code

    discounted = subtotal - coupon_discount

    cfg = StoreConfig.get_solo()
    if not items:
        delivery_fee = Decimal("0")
        small_cart_fee = Decimal("0")
    else:
        delivery_fee = (
            Decimal("0") if subtotal >= cfg.free_delivery_threshold else cfg.delivery_fee
        )
        small_cart_fee = cfg.small_cart_fee if subtotal < cfg.small_cart_threshold else Decimal("0")

    taxable = discounted + delivery_fee + small_cart_fee
    tax = _q(taxable * cfg.tax_percent / 100)
    grand_total = _q(discounted + delivery_fee + small_cart_fee + tax)

    return {
        "subtotal": _q(subtotal),
        "mrp_savings": _q(mrp_savings),
        "coupon_code": coupon_code,
        "coupon_discount": _q(coupon_discount),
        "delivery_fee": _q(delivery_fee),
        "small_cart_fee": _q(small_cart_fee),
        "tax": tax,
        "grand_total": grand_total,
        "item_count": len(items),
    }
