from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

TWO_PLACES = Decimal("0.01")


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        FLAT = "flat", "Flat amount"
        PERCENT = "percent", "Percentage"

    code = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=200, blank=True, default="")
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=8, decimal_places=2, help_text="Flat amount or percentage")
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cap on discount (mainly for percentage coupons)",
    )
    usage_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Global redemption limit (blank = unlimited)"
    )
    per_user_limit = models.PositiveIntegerField(default=1)
    first_order_only = models.BooleanField(default=False)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    times_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "coupons"
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        super().save(*args, **kwargs)

    def calculate_discount(self, subtotal):
        """Discount for a given subtotal, capped at max_discount and never above subtotal."""
        if self.discount_type == self.DiscountType.FLAT:
            discount = self.value
        else:
            discount = subtotal * self.value / 100
        if self.max_discount is not None:
            discount = min(discount, self.max_discount)
        discount = min(discount, subtotal)
        return discount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    def check_eligibility(self, user, subtotal):
        """Return (is_eligible, reason). reason is None when eligible."""
        now = timezone.now()
        if not self.is_active:
            return False, "This coupon is no longer active."
        if now < self.valid_from:
            return False, "This coupon is not yet valid."
        if now > self.valid_until:
            return False, "This coupon has expired."
        if subtotal < self.min_order_value:
            return False, f"Add items worth ₹{self.min_order_value} to use this coupon."
        if self.usage_limit is not None and self.times_used >= self.usage_limit:
            return False, "This coupon has reached its usage limit."
        used_by_user = self.redemptions.filter(user=user).count()
        if used_by_user >= self.per_user_limit:
            return False, "You have already used this coupon."
        if self.first_order_only and user.orders.exists():
            return False, "This coupon is valid on your first order only."
        return True, None


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coupon_redemptions",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_redemptions",
    )
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "coupon_redemptions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.coupon.code} by {self.user.phone}"
