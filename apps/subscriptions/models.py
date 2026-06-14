from django.conf import settings
from django.db import models


class Subscription(models.Model):
    """A recurring milk order: a SKU delivered on a frequency, paid from the wallet."""

    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        ALTERNATE = "alternate", "Alternate days"
        WEEKDAYS = "weekdays", "Weekdays (Mon–Fri)"
        CUSTOM = "custom", "Custom calendar"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    quantity = models.PositiveIntegerField(default=1, help_text="Default units delivered per day")
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    custom_days = models.JSONField(
        default=list,
        blank=True,
        help_text="For CUSTOM frequency: list of ISO dates, e.g. ['2026-06-20', '2026-06-22']",
    )
    address = models.ForeignKey(
        "addresses.Address",
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    preferred_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Preferred morning delivery time",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscriptions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Subscription #{self.pk} — {self.user.phone} ({self.frequency})"

    @property
    def daily_cost(self):
        """Indicative cost of one day's delivery at the current price."""
        return self.variant.price * self.quantity


class SubscriptionVacation(models.Model):
    """A date range during which an active subscription is paused (no generation)."""

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="vacations",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscription_vacations"
        ordering = ["start_date"]

    def __str__(self):
        return f"Vacation {self.start_date}–{self.end_date} (sub #{self.subscription_id})"


class SubscriptionDelivery(models.Model):
    """One day's delivery for a subscription.

    Doubles as the per-day override store: a row created ahead of the nightly run
    with status SKIPPED (a one-off skip) or an overridden ``quantity`` (a one-day
    quantity change) is honoured by the generator. After generation it records the
    linked order, charged amount and outcome.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        SKIPPED = "skipped", "Skipped"
        DELIVERED = "delivered", "Delivered"
        FAILED_BALANCE = "failed_balance", "Failed — insufficient balance"

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    date = models.DateField()
    quantity = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_deliveries",
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_deliveries"
        ordering = ["-date"]
        unique_together = ("subscription", "date")

    def __str__(self):
        return f"Delivery {self.date} — sub #{self.subscription_id} ({self.status})"

    @property
    def is_generated(self):
        """True once the nightly job has created an order for this day."""
        return self.order_id is not None
