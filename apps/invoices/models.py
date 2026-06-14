from django.db import models


class Invoice(models.Model):
    """A billing document for a single order.

    Totals are snapshotted from the order at issue time so a later order edit can
    never change an already-issued invoice. The human-readable ``number`` is filled
    once the row has a primary key (see :meth:`save`).
    """

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="invoice",
    )
    number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    small_cart_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    issued_at = models.DateTimeField(auto_now_add=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-issued_at"]

    def __str__(self):
        return self.number or f"Invoice (draft) for order {self.order_id}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            # Globally unique, human-readable: INV-<issue year>-<zero-padded pk>.
            self.number = f"INV-{self.issued_at:%Y}-{self.pk:06d}"
            super().save(update_fields=["number"])
