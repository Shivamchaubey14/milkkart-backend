from django.conf import settings
from django.db import models


class Category(models.TextChoices):
    ORDER = "order", "Order"
    PROMO = "promo", "Promotion"
    SUBSCRIPTION = "subscription", "Subscription"
    SYSTEM = "system", "System"


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=15, choices=Category.choices, default=Category.SYSTEM)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.category}: {self.title}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    # Channel toggles
    push_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    # Category opt-ins
    order_updates = models.BooleanField(default=True)
    promotions = models.BooleanField(default=True)
    subscription_reminders = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_preferences"

    def __str__(self):
        return f"Preferences({self.user.phone})"


class DeviceToken(models.Model):
    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        WEB = "web", "Web"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, choices=Platform.choices, default=Platform.ANDROID)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "device_tokens"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.platform} token for {self.user.phone}"
