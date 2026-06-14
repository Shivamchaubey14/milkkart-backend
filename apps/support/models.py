import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

RATING_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]


class FAQ(models.Model):
    """A help-centre question/answer, optionally grouped by topic."""

    topic = models.CharField(max_length=80, blank=True, default="")
    question = models.CharField(max_length=255)
    answer = models.TextField()
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "faqs"
        ordering = ["topic", "sort_order", "id"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class OrderReview(models.Model):
    """A post-delivery rating of an order and the rider who delivered it."""

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="review",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="order_reviews",
    )
    order_rating = models.PositiveSmallIntegerField(validators=RATING_VALIDATORS)
    rider_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=RATING_VALIDATORS
    )
    comment = models.TextField(blank=True, default="")
    photos = models.JSONField(default=list, blank=True, help_text="List of photo URLs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "order_reviews"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Review {self.order_rating}★ for order {self.order_id}"


class ProductRating(models.Model):
    """A customer's rating of a product, aggregated onto the product page."""

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ratings",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_ratings",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_ratings",
    )
    rating = models.PositiveSmallIntegerField(validators=RATING_VALIDATORS)
    comment = models.TextField(blank=True, default="")
    photos = models.JSONField(default=list, blank=True, help_text="List of photo URLs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_ratings"
        ordering = ["-created_at"]
        # One rating per product per order (a re-rate updates the same row).
        unique_together = ("user", "product", "order")

    def __str__(self):
        return f"{self.rating}★ for {self.product_id} by {self.user_id}"


class SupportTicket(models.Model):
    """An order-level complaint resolved by an agent via replacement or refund."""

    class Reason(models.TextChoices):
        WRONG_ITEM = "wrong_item", "Wrong item"
        MISSING_ITEM = "missing_item", "Missing item"
        DAMAGED_ITEM = "damaged_item", "Damaged item"
        QUALITY_ISSUE = "quality_issue", "Quality issue"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    class Resolution(models.TextChoices):
        NONE = "none", "None"
        REPLACEMENT = "replacement", "Replacement"
        REFUND = "refund", "Wallet refund"

    ticket_number = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_tickets",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    reason = models.CharField(max_length=20, choices=Reason.choices, default=Reason.OTHER)
    subject = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    photos = models.JSONField(default=list, blank=True, help_text="List of photo URLs")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    resolution_type = models.CharField(
        max_length=12, choices=Resolution.choices, default=Resolution.NONE
    )
    resolution_note = models.TextField(blank=True, default="")
    refund_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "support_tickets"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Ticket {self.ticket_number} — {self.status}"

    @property
    def is_open(self):
        return self.status in (self.Status.OPEN, self.Status.IN_PROGRESS)


class TicketMessage(models.Model):
    """A message in a support-ticket thread, from the customer or an agent."""

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ticket_messages",
    )
    is_staff = models.BooleanField(default=False)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_messages"
        ordering = ["created_at"]

    def __str__(self):
        who = "agent" if self.is_staff else "customer"
        return f"Message from {who} on {self.ticket_id}"
