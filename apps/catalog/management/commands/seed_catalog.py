from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.catalog.models import Category, Product, ProductVariant

# category -> list of products; each product: (name, brand, fat%, [variants])
# variant: (label, price, mrp, unit, quantity_value)
CATALOG = {
    "Milk": [
        ("Full Cream Milk", "Amul", "6.0", [
            ("500 ml", 28, 30, "ml", 500),
            ("1 L", 54, 58, "l", 1),
        ]),
        ("Toned Milk", "Amul", "3.0", [
            ("500 ml", 24, 26, "ml", 500),
            ("1 L", 46, 50, "l", 1),
        ]),
        ("Skimmed Milk", "Mother Dairy", "0.5", [
            ("500 ml", 22, 24, "ml", 500),
        ]),
    ],
    "Curd & Yogurt": [
        ("Fresh Curd", "Amul", None, [
            ("400 g", 35, 38, "g", 400),
            ("1 kg", 75, 80, "kg", 1),
        ]),
        ("Greek Yogurt", "Epigamia", None, [("100 g", 45, 50, "g", 100)]),
        ("Mango Lassi", "Amul", None, [("200 ml", 30, 35, "ml", 200)]),
        ("Buttermilk", "Mother Dairy", None, [("500 ml", 20, 22, "ml", 500)]),
    ],
    "Paneer & Cheese": [
        ("Fresh Paneer", "Amul", None, [
            ("200 g", 80, 90, "g", 200),
            ("500 g", 180, 200, "g", 500),
        ]),
        ("Mozzarella Cheese", "Go", None, [("200 g", 120, 135, "g", 200)]),
        ("Cheese Slices", "Amul", None, [("Pack of 10", 95, 105, "pcs", 10)]),
        ("Cream Cheese", "Britannia", None, [("200 g", 110, 125, "g", 200)]),
    ],
    "Butter & Ghee": [
        ("Salted Butter", "Amul", None, [
            ("100 g", 52, 56, "g", 100),
            ("500 g", 245, 265, "g", 500),
        ]),
        ("Unsalted Butter", "Amul", None, [("100 g", 55, 60, "g", 100)]),
        ("Pure Desi Ghee", "Amul", None, [
            ("500 ml", 320, 350, "ml", 500),
            ("1 L", 620, 680, "l", 1),
        ]),
    ],
    "Cream & Condensed": [
        ("Fresh Cream", "Amul", None, [("200 ml", 55, 60, "ml", 200)]),
        ("Whipping Cream", "Rich's", None, [("250 ml", 85, 95, "ml", 250)]),
        ("Condensed Milk", "Nestle", None, [("200 g", 60, 65, "g", 200)]),
        ("Malai", "Mother Dairy", None, [("100 g", 40, 45, "g", 100)]),
    ],
    "Ice Cream": [
        ("Vanilla Ice Cream", "Kwality Walls", None, [
            ("Cup 100 ml", 30, 35, "ml", 100),
            ("Family Pack 1 L", 180, 200, "l", 1),
        ]),
        ("Chocolate Cone", "Kwality Walls", None, [("1 piece", 40, 45, "pcs", 1)]),
        ("Mango Bar", "Kwality Walls", None, [("1 piece", 25, 30, "pcs", 1)]),
        ("Butterscotch Tub", "Amul", None, [("500 ml", 120, 140, "ml", 500)]),
    ],
}


class Command(BaseCommand):
    help = "Seed the catalog with dairy categories, products and variants (SKUs)"

    def handle(self, *args, **options):
        variant_count = 0
        for sort_order, (cat_name, products) in enumerate(CATALOG.items()):
            category, created = Category.objects.get_or_create(
                name=cat_name,
                defaults={"sort_order": sort_order},
            )
            action = "Created" if created else "Exists"
            self.stdout.write(f"  {action} category: {cat_name}")

            for name, brand, fat, variants in products:
                product, _ = Product.objects.get_or_create(
                    name=name,
                    defaults={"category": category, "brand": brand},
                )
                product_slug = slugify(name)
                for idx, (label, price, mrp, unit, qty) in enumerate(variants):
                    _, v_created = ProductVariant.objects.get_or_create(
                        sku=f"{product_slug}-{slugify(label)}",
                        defaults={
                            "product": product,
                            "label": label,
                            "price": Decimal(str(price)),
                            "mrp": Decimal(str(mrp)),
                            "unit": unit,
                            "quantity_value": Decimal(str(qty)),
                            "fat_percent": Decimal(fat) if fat else None,
                            "stock": 50,
                            "is_default": idx == 0,
                        },
                    )
                    if v_created:
                        variant_count += 1
                        self.stdout.write(f"    + {name} — {label}")

        products_total = Product.objects.count()
        variants_total = ProductVariant.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! {products_total} products, {variants_total} variants in catalog."
            )
        )
