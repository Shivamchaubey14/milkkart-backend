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
