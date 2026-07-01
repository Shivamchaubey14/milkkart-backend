from django.db import models


class ServiceableArea(models.Model):
    """A delivery zone keyed by pincode, optionally refined by a geofence circle.

    Serviceability is primarily a pincode lookup; when ``center_lat``/``center_lng``
    and ``radius_km`` are set and the address has coordinates, the point must also
    fall inside the circle.
    """

    pincode = models.CharField(max_length=10, unique=True, db_index=True)
    area_name = models.CharField(max_length=120, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)
    delivery_eta_minutes = models.PositiveIntegerField(
        null=True, blank=True, help_text="Typical delivery time for this area"
    )
    center_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    center_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    radius_km = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Geofence radius around the centre, in km",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "serviceable_areas"
        ordering = ["pincode"]

    def __str__(self):
        label = self.area_name or self.city or "area"
        return f"{self.pincode} ({label})"

    @property
    def has_geofence(self):
        return None not in (self.center_lat, self.center_lng, self.radius_km)


class DeliveryZone(models.Model):
    """A delivery area drawn on a map (admin dashboard) and stored as GeoJSON.

    Unlike ``ServiceableArea`` (keyed by pincode), a zone is a free-form polygon
    that can cover a whole region or a small pocket inside a larger one. An
    address point is serviceable when it falls inside an active zone's polygon;
    on overlap the higher ``priority`` wins.
    """

    name = models.CharField(max_length=120)
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    # GeoJSON geometry: {"type": "Polygon"|"MultiPolygon", "coordinates": [...]}
    # with coordinates as [lng, lat] pairs (GeoJSON order).
    polygon = models.JSONField()
    is_active = models.BooleanField(default=True)
    delivery_eta_minutes = models.PositiveIntegerField(null=True, blank=True)
    priority = models.IntegerField(
        default=0, help_text="Higher wins when zones overlap (e.g. a small zone over a big one)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "delivery_zones"
        ordering = ["-priority", "name"]

    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"


class WaitlistEntry(models.Model):
    """A customer who asked to be notified when we start delivering to their area.

    Captured from the "We're not in your area yet" screen (mobile/web): a phone
    number tied to the pincode they were interested in. One row per
    (phone, pincode) — asking again just refreshes the same entry.
    """

    phone = models.CharField(max_length=20, db_index=True)
    pincode = models.CharField(max_length=10, db_index=True)
    city = models.CharField(max_length=120, blank=True, default="")
    notified = models.BooleanField(
        default=False, help_text="Set once we've told them their area went live"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "serviceability_waitlist"
        ordering = ["-created_at"]
        unique_together = ("phone", "pincode")
        verbose_name_plural = "Waitlist entries"

    def __str__(self):
        return f"{self.phone} @ {self.pincode}"
