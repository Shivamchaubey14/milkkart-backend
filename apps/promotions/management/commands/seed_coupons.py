from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.promotions.models import Coupon

# code -> defaults (validity is set relative to now at run time)
COUPONS = {
    "WELCOME50": dict(
        description="₹50 off your first order",
        discount_type=Coupon.DiscountType.FLAT,
        value=Decimal("50"),
        min_order_value=Decimal("199"),
        first_order_only=True,
    ),
    "DAIRY10": dict(
        description="10% off, up to ₹40",
        discount_type=Coupon.DiscountType.PERCENT,
        value=Decimal("10"),
        max_discount=Decimal("40"),
        min_order_value=Decimal("149"),
    ),
    "FLAT20": dict(
        description="₹20 off on ₹99+",
        discount_type=Coupon.DiscountType.FLAT,
        value=Decimal("20"),
        min_order_value=Decimal("99"),
    ),
}


class Command(BaseCommand):
    help = "Seed development coupons"

    def handle(self, *args, **options):
        now = timezone.now()
        for code, defaults in COUPONS.items():
            _, created = Coupon.objects.get_or_create(
                code=code,
                defaults={
                    **defaults,
                    "valid_from": now - timedelta(days=1),
                    "valid_until": now + timedelta(days=90),
                },
            )
            if created:
                self.stdout.write(f"  + {code}")

        total = Coupon.objects.count()
        self.stdout.write(self.style.SUCCESS(f"\nDone! {total} coupons available."))
