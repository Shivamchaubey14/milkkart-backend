import uuid

from django.conf import settings
from django.db import models


class Payment(models.Model):
    class Method(models.TextChoices):
        COD = "cod", "Cash on Delivery"
        ONLINE = "online", "Online"
        WALLET = "wallet", "MilkKart Wallet"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    payment_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payment",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.CREATED,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Gateway fields (Razorpay-style)
    gateway_order_id = models.CharField(max_length=100, blank=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True)
    gateway_signature = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.payment_id} — {self.status}"

    @property
    def is_paid(self):
        return self.status == self.Status.SUCCESS


class PaymentWebhookEvent(models.Model):
    """A received gateway webhook, logged for idempotency and audit.

    A gateway may deliver the same event more than once; ``event_id`` is unique so
    a replay is recognised and skipped.
    """

    event_id = models.CharField(max_length=120, unique=True)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_webhook_events"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} ({self.event_id})"
