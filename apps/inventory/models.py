from django.conf import settings
from django.db import models


class StockMovement(models.Model):
    """An append-only ledger entry for every change to a variant's stock.

    ``delta`` is signed (+restock, -sale); ``balance_after`` snapshots the stock
    level immediately after the movement so history is auditable without replay.
    """

    class Reason(models.TextChoices):
        RESTOCK = "restock", "Restock"
        SALE = "sale", "Sale"
        CANCELLATION = "cancellation", "Cancellation"
        SUBSCRIPTION = "subscription", "Subscription"
        ADJUSTMENT = "adjustment", "Manual adjustment"
        DAMAGE = "damage", "Damage / wastage"

    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    delta = models.IntegerField(help_text="Signed change in stock (+restock, -sale)")
    reason = models.CharField(max_length=15, choices=Reason.choices)
    balance_after = models.PositiveIntegerField()
    note = models.CharField(max_length=200, blank=True, default="")
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movements"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["variant", "-created_at"])]

    def __str__(self):
        return f"{self.variant_id} {self.delta:+d} ({self.reason})"
