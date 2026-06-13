import secrets

from django.conf import settings
from django.db import models


def generate_delivery_otp():
    return f"{secrets.randbelow(1000000):06d}"


class DeliveryPartner(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delivery_partner",
    )
    vehicle_number = models.CharField(max_length=20, blank=True, default="")
    is_on_duty = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    current_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "delivery_partners"

    def __str__(self):
        return f"Rider({self.user.phone})"


class DeliveryAssignment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        ACCEPTED = "accepted", "Accepted"
        PICKED_UP = "picked_up", "Picked up"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="assignment",
    )
    rider = models.ForeignKey(
        DeliveryPartner,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ASSIGNED)
    delivery_otp = models.CharField(max_length=6, default=generate_delivery_otp)
    proof_photo = models.CharField(max_length=255, blank=True, default="")
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "delivery_assignments"
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.order.order_number} → {self.rider.user.phone} ({self.status})"

    @property
    def is_active(self):
        return self.status not in (self.Status.DELIVERED, self.Status.CANCELLED)
