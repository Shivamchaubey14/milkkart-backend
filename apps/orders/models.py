import uuid

from django.conf import settings
from django.db import models


class DeliverySlot(models.Model):
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity = models.PositiveIntegerField(default=20)
    booked = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "delivery_slots"
        ordering = ["date", "start_time"]
        unique_together = ("date", "start_time", "end_time")

    def __str__(self):
        return f"{self.date} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    @property
    def available(self):
        return self.capacity - self.booked

    @property
    def is_full(self):
        return self.booked >= self.capacity


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order_number = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    small_cart_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, help_text="Grand total payable")
    coupon = models.ForeignKey(
        "promotions.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    address = models.ForeignKey(
        "addresses.Address",
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders",
    )
    address_snapshot = models.TextField(default="", help_text="Address text at time of order")
    delivery_slot = models.ForeignKey(
        DeliverySlot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    notes = models.TextField(blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders"
        ordering = ["-placed_at"]

    def __str__(self):
        return f"Order {self.order_number} — {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=200)
    variant_label = models.CharField(max_length=100, blank=True, default="")
    product_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField()

    class Meta:
        db_table = "order_items"

    def __str__(self):
        label = f" ({self.variant_label})" if self.variant_label else ""
        return f"{self.product_name}{label} x{self.quantity}"

    @property
    def subtotal(self):
        return self.product_price * self.quantity
