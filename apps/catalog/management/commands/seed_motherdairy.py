"""Seed the catalog with a real Mother Dairy product range.

Product names, pack sizes and prices mirror Mother Dairy's actual line-up; images
are served by the web client from ``images/products/<slug>.<ext>``. Running this
deactivates any non-Mother-Dairy catalog so the storefront shows only these items.
Idempotent: re-running updates in place.
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.catalog.models import Category, Product, ProductVariant

ML = ProductVariant.Unit.ML
L = ProductVariant.Unit.L
G = ProductVariant.Unit.G
KG = ProductVariant.Unit.KG
PCS = ProductVariant.Unit.PCS

# category, name, image (path under web /images/products/), unit, tags,
# variants: (label, quantity_value, price, mrp, stock)
PRODUCTS = [
    ("Milk", "Full Cream Milk", "milk-full-cream.png", ML, "milk full cream dairy",
     [("500 ml", 500, "36", "36", 200), ("1 L", 1, "72", "72", 200)]),
    ("Milk", "Toned Milk", "milk-toned.jpg", ML, "milk toned dairy",
     [("500 ml", 500, "27", "27", 200), ("1 L", 1, "56", "56", 200)]),
    ("Milk", "Cow Milk", "milk-cow.png", ML, "cow milk dairy",
     [("500 ml", 500, "30", "30", 150), ("1 L", 1, "60", "60", 150)]),
    ("Milk", "Token Milk", "milk-token.png", ML, "token milk economy",
     [("500 ml", 500, "25", "25", 150)]),
    ("Milk", "Standardised Milk", "milk-standardized.png", ML, "standardised milk",
     [("500 ml", 500, "33", "33", 120), ("1 L", 1, "66", "66", 120)]),

    ("Curd & Yogurt", "Classic Dahi", "dahi-classic.png", G, "curd dahi yogurt",
     [("400 g", 400, "40", "42", 120), ("1 kg", 1000, "85", "90", 80)]),
    ("Curd & Yogurt", "Mishti Doi", "mishti-doi.png", G, "mishti doi sweet curd bengali",
     [("200 g", 200, "45", "48", 90)]),
    ("Curd & Yogurt", "Nutrifit Probiotic Dahi", "dahi-probiotic.png", G, "probiotic dahi curd",
     [("400 g", 400, "50", "52", 80)]),
    ("Curd & Yogurt", "Fruit Yoghurt", "fruit-yoghurt.png", G, "fruit yoghurt",
     [("100 g", 100, "25", "25", 100)]),

    ("Paneer & Cheese", "Paneer", "paneer.png", G, "paneer cottage cheese",
     [("200 g", 200, "92", "95", 100), ("400 g", 400, "174", "180", 70)]),
    ("Paneer & Cheese", "Cheese Slices", "cheese-slice.png", G, "cheese slices",
     [("200 g", 200, "140", "150", 60)]),
    ("Paneer & Cheese", "Cheese Cubes", "cheese-cubes.png", G, "cheese cubes",
     [("180 g", 180, "135", "140", 60)]),
    ("Paneer & Cheese", "Cheese Spread", "cheese-spread.png", G, "cheese spread",
     [("180 g", 180, "95", "100", 60)]),
    ("Paneer & Cheese", "Cheese Block", "cheese-block.png", G, "cheese block mozzarella",
     [("200 g", 200, "140", "145", 50)]),

    ("Butter & Ghee", "Butter", "butter.png", G, "butter table",
     [("100 g", 100, "58", "62", 120), ("500 g", 500, "285", "305", 70)]),
    ("Butter & Ghee", "Pure Ghee", "ghee.png", ML, "ghee desi pure",
     [("500 ml", 500, "330", "345", 80), ("1 L", 1, "645", "675", 50)]),

    ("Beverages", "Lassi", "lassi.png", ML, "lassi yogurt drink",
     [("200 ml", 200, "20", "20", 150), ("400 ml", 400, "35", "35", 120)]),
    ("Beverages", "Chaach (Buttermilk)", "chach.png", ML, "chaach buttermilk masala",
     [("500 ml", 500, "25", "25", 120), ("200 ml", 200, "10", "10", 100)]),

    ("Sweets", "Gulab Jamun", "gulab-jamun.png", G, "gulab jamun sweet dessert",
     [("500 g", 500, "150", "160", 80)]),
    ("Sweets", "Rasgulla", "rasgulla.png", KG, "rasgulla sweet bengali dessert",
     [("1 kg", 1000, "180", "190", 70)]),
    ("Sweets", "Rasmalai", "rasmalai.png", KG, "rasmalai sweet dessert",
     [("1 kg", 1000, "220", "230", 60)]),

    ("Ice Cream", "Vanilla Ice Cream", "ic-vanilla.png", ML, "ice cream vanilla tub",
     [("700 ml", 700, "150", "160", 90)]),
    ("Ice Cream", "Butterscotch Ice Cream", "ic-butterscotch.png", ML, "ice cream butterscotch tub",
     [("700 ml", 700, "160", "170", 90)]),
    ("Ice Cream", "Chocolate Ice Cream", "ic-chocolate.png", ML, "ice cream chocolate tub",
     [("700 ml", 700, "170", "180", 90)]),
    ("Ice Cream", "Mango Magic Ice Cream", "ic-mango.png", ML, "ice cream mango tub",
     [("700 ml", 700, "150", "160", 90)]),
    ("Ice Cream", "Choco Bar", "ic-choco-bar.png", PCS, "ice cream choco bar stick",
     [("1 pc", 1, "20", "20", 200)]),

    ("Pantry", "Dairy Whitener", "dairy-whitener.png", G, "dairy whitener milk powder",
     [("200 g", 200, "110", "115", 80), ("1 kg", 1000, "500", "520", 40)]),
    ("Pantry", "UHT Cream", "uht-cream.png", ML, "cream uht cooking",
     [("200 ml", 200, "75", "78", 70)]),

    ("Bread & Bakery", "Sandwich Bread", "sandwich-bread.jpg", G, "bread sandwich bakery",
     [("350 g", 350, "40", "42", 100)]),
    ("Bread & Bakery", "Brown Bread", "brown-bread.jpg", G, "bread brown wheat bakery",
     [("350 g", 350, "45", "48", 100)]),
]

CATEGORY_ORDER = [
    "Milk", "Curd & Yogurt", "Paneer & Cheese", "Butter & Ghee",
    "Beverages", "Sweets", "Ice Cream", "Pantry", "Bread & Bakery",
]


class Command(BaseCommand):
    help = "Seed the catalog with Mother Dairy products (deactivates other catalog)."

    def handle(self, *args, **options):
        # Hide any pre-existing (non-Mother-Dairy) catalog instead of deleting it,
        # so existing orders/subscriptions keep their references.
        Category.objects.update(is_active=False)
        Product.objects.update(is_active=False)
        ProductVariant.objects.update(is_active=False)

        categories = {}
        for order, name in enumerate(CATEGORY_ORDER):
            cat, _ = Category.objects.get_or_create(name=name)
            cat.is_active = True
            cat.sort_order = order
            cat.save()
            categories[name] = cat

        products = variants = 0
        for cat_name, name, image, unit, tags, variant_specs in PRODUCTS:
            product, _ = Product.objects.get_or_create(
                name=name, defaults={"category": categories[cat_name]}
            )
            product.category = categories[cat_name]
            product.brand = "Mother Dairy"
            product.image_url = f"images/products/{image}"
            product.tags = tags
            product.description = f"{name} from Mother Dairy — fresh and quality assured."
            product.is_active = True
            product.save()
            products += 1

            for idx, (label, qval, price, mrp, stock) in enumerate(variant_specs):
                sku = slugify(f"md-{name}-{label}")
                ProductVariant.objects.update_or_create(
                    sku=sku,
                    defaults={
                        "product": product,
                        "label": label,
                        "unit": unit,
                        "quantity_value": qval,
                        "price": price,
                        "mrp": mrp,
                        "stock": stock,
                        "is_default": idx == 0,
                        "is_active": True,
                    },
                )
                variants += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {products} Mother Dairy products, {variants} variants "
                f"across {len(categories)} categories."
            )
        )
