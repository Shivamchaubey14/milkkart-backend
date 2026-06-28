from django.conf import settings
from django.db import models


class StoreConfig(models.Model):
    """Operator-editable storefront fees (FR-CART-02).

    A single row (pk=1) holds the live values the cart bill engine uses. The
    settings.* values (env-overridable) are only the initial defaults — once this
    row exists, the admin edits here win, so fees can be changed without a deploy.
    Set any amount to 0 to switch that fee off entirely.
    """

    free_delivery_threshold = models.DecimalField(
        max_digits=8, decimal_places=2, default=settings.FREE_DELIVERY_THRESHOLD,
        help_text="Order subtotal at/above which delivery is free.",
    )
    delivery_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=settings.DELIVERY_FEE,
        help_text="Delivery charge below the free-delivery threshold. 0 = always free.",
    )
    small_cart_threshold = models.DecimalField(
        max_digits=8, decimal_places=2, default=settings.SMALL_CART_THRESHOLD,
        help_text="Subtotal below which a small-cart fee applies. 0 = never.",
    )
    small_cart_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=settings.SMALL_CART_FEE,
        help_text="Small-cart fee amount. 0 = no small-cart fee.",
    )
    tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=settings.TAX_PERCENT,
        help_text="Tax percentage applied to the taxable amount. 0 = no tax.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "store_config"
        verbose_name = "Store configuration"
        verbose_name_plural = "Store configuration"

    def __str__(self):
        return "Store configuration"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce a single config row
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """The single config row, created from the settings defaults on first use."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BulkImport(models.Model):
    """An async bulk spreadsheet import (riders / customers / inventory).

    A row is created per upload; a background worker processes the parsed rows
    and updates progress + per-row errors here, which the admin UI polls.
    """

    class Kind(models.TextChoices):
        CUSTOMERS = "customers", "Customers"
        RIDERS = "riders", "Riders"
        INVENTORY = "inventory", "Inventory"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    filename = models.CharField(max_length=255, blank=True, default="")
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    # Per-row errors: [{"row": <1-based incl. header>, "message": "..."}]
    errors = models.JSONField(default=list, blank=True)
    message = models.CharField(max_length=255, blank=True, default="")  # fatal error, if any
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="bulk_imports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bulk_imports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"BulkImport #{self.pk} {self.kind} ({self.status})"

    @property
    def progress_percent(self):
        if not self.total_rows:
            return 100 if self.status in (self.Status.COMPLETED, self.Status.FAILED) else 0
        return round(self.processed_rows / self.total_rows * 100)
