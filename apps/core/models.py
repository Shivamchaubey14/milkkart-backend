from django.conf import settings
from django.db import models


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
