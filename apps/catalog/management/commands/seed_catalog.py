from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalog.models import Category, Product

CATALOG = {
    "Milk": [
        ("Full Cream Milk 500ml", 28, 30, "ml", 500),
        ("Full Cream Milk 1L", 54, 58, "l", 1),
        ("Toned Milk 500ml", 24, 26, "ml", 500),
        ("Toned Milk 1L", 46, 50, "l", 1),
        ("Skimmed Milk 500ml", 22, 24, "ml", 500),
    ],
    "Curd & Yogurt": [
        ("Fresh Curd 400g", 35, 38, "g", 400),
        ("Fresh Curd 1kg", 75, 80, "kg", 1),
        ("Greek Yogurt 100g", 45, 50, "g", 100),
        ("Mango Lassi 200ml", 30, 35, "ml", 200),
        ("Buttermilk 500ml", 20, 22, "ml", 500),
    ],
    "Paneer & Cheese": [
        ("Fresh Paneer 200g", 80, 90, "g", 200),
        ("Fresh Paneer 500g", 180, 200, "g", 500),
        ("Mozzarella Cheese 200g", 120, 135, "g", 200),
        ("Cheese Slices 10pcs", 95, 105, "pcs", 10),
        ("Cream Cheese 200g", 110, 125, "g", 200),
    ],
    "Butter & Ghee": [
        ("Salted Butter 100g", 52, 56, "g", 100),
        ("Salted Butter 500g", 245, 265, "g", 500),
        ("Unsalted Butter 100g", 55, 60, "g", 100),
        ("Pure Desi Ghee 500ml", 320, 350, "ml", 500),
        ("Pure Desi Ghee 1L", 620, 680, "l", 1),
    ],
    "Cream & Condensed": [
        ("Fresh Cream 200ml", 55, 60, "ml", 200),
        ("Whipping Cream 250ml", 85, 95, "ml", 250),
        ("Condensed Milk 200g", 60, 65, "g", 200),
        ("Malai 100g", 40, 45, "g", 100),
    ],
    "Ice Cream": [
        ("Vanilla Cup 100ml", 30, 35, "ml", 100),
        ("Chocolate Cone", 40, 45, "pcs", 1),
        ("Mango Bar", 25, 30, "pcs", 1),
        ("Family Pack Vanilla 1L", 180, 200, "l", 1),
        ("Butterscotch Tub 500ml", 120, 140, "ml", 500),
    ],
}


class Command(BaseCommand):
    help = "Seed the catalog with dairy categories and products"

    def handle(self, *args, **options):
        for sort_order, (cat_name, products) in enumerate(CATALOG.items()):
            category, created = Category.objects.get_or_create(
                name=cat_name,
                defaults={"sort_order": sort_order},
            )
            action = "Created" if created else "Exists"
            self.stdout.write(f"  {action} category: {cat_name}")

            for name, price, mrp, unit, qty in products:
                _, p_created = Product.objects.get_or_create(
                    name=name,
                    defaults={
                        "category": category,
                        "price": Decimal(str(price)),
                        "mrp": Decimal(str(mrp)),
                        "unit": unit,
                        "quantity_value": Decimal(str(qty)),
                        "stock": 50,
                    },
                )
                if p_created:
                    self.stdout.write(f"    + {name}")

        total = Product.objects.count()
        self.stdout.write(self.style.SUCCESS(f"\nDone! {total} products in catalog."))
