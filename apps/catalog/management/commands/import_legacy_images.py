import os
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from apps.catalog.models import Product, ProductImage


class Command(BaseCommand):
    help = (
        "Import legacy static product images (served by milkkart-web) into the "
        "backend media store as ProductImage records, so all product images are "
        "served by the backend. Idempotent: products that already have an "
        "uploaded image are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--web-dir",
            default=str(Path(settings.BASE_DIR).parent / "milkkart-web"),
            help="Path to the milkkart-web folder (which contains /images).",
        )

    def handle(self, *args, **opts):
        web = Path(opts["web_dir"])
        created = skipped = missing = 0

        for product in Product.objects.prefetch_related("images"):
            if product.images.exists():
                skipped += 1
                continue
            rel = (product.image_url or "").lstrip("/")
            if not rel:
                skipped += 1
                continue
            src = web / rel  # e.g. images/products/brown-bread.jpg
            if not src.exists():
                missing += 1
                self.stderr.write(self.style.WARNING(f"missing file for {product.name}: {src}"))
                continue
            with src.open("rb") as fh:
                pi = ProductImage(product=product, alt_text=product.name, sort_order=0)
                pi.image.save(os.path.basename(rel), File(fh), save=True)
            created += 1
            self.stdout.write(f"imported {product.name} <- {rel}")

        self.stdout.write(
            self.style.SUCCESS(f"Done. created={created} skipped={skipped} missing={missing}")
        )
