from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "categories"
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """A sellable product. Pricing and stock live on its variants (SKUs)."""

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    brand = models.CharField(max_length=120, blank=True, default="")
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=255, blank=True, default="", help_text="Comma-separated search tags")
    is_active = models.BooleanField(default=True)
    # Denormalised rating aggregates, maintained by apps.support on each new rating.
    rating_sum = models.PositiveIntegerField(default=0)
    rating_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def rating_average(self):
        if self.rating_count:
            return round(self.rating_sum / self.rating_count, 1)
        return 0.0

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def default_variant(self):
        """The variant shown on the product card — explicit default, else cheapest active."""
        active = [v for v in self.variants.all() if v.is_active]
        if not active:
            return None
        return sorted(active, key=lambda v: (not v.is_default, v.price))[0]


class ProductVariant(models.Model):
    """A stock-keeping unit: a specific size/fat% of a product with its own price and stock."""

    class Unit(models.TextChoices):
        ML = "ml", "Millilitres"
        L = "l", "Litres"
        G = "g", "Grams"
        KG = "kg", "Kilograms"
        PCS = "pcs", "Pieces"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    label = models.CharField(max_length=100, help_text="e.g. 500 ml, 1 L, Pack of 6")
    sku = models.CharField(max_length=50, unique=True)
    unit = models.CharField(max_length=5, choices=Unit.choices, default=Unit.PCS)
    quantity_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=1,
        help_text="e.g. 500 for 500ml",
    )
    fat_percent = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Fat content %, where applicable",
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    mrp = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    stock = models.PositiveIntegerField(default=0)
    barcode = models.CharField(max_length=50, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_variants"
        ordering = ["price"]

    def __str__(self):
        return f"{self.product.name} — {self.label}"

    @property
    def discount_percent(self):
        if self.mrp > 0:
            return round((1 - self.price / self.mrp) * 100, 1)
        return 0

    @property
    def in_stock(self):
        return self.stock > 0


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "product_images"
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.product.name} - Image {self.sort_order}"
