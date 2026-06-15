"""Serviceability checks: can we deliver to a pincode / location?

The model is fail-open *until configured*: with no active areas in the table at
all, everywhere is serviceable (geofencing not yet set up). Once any area exists,
only matching pincodes (and, where set, points inside the geofence) are served.
``SERVICEABILITY_ENFORCED=False`` disables the gate entirely.
"""

import math

from django.conf import settings

from .models import ServiceableArea


def _enforced():
    return getattr(settings, "SERVICEABILITY_ENFORCED", True)


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lng2) - float(lng1))
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def area_for_pincode(pincode):
    """Return the active ServiceableArea for ``pincode``, or None."""
    if not pincode:
        return None
    return ServiceableArea.objects.filter(pincode=str(pincode).strip(), is_active=True).first()


def check(pincode, lat=None, lng=None):
    """Resolve serviceability for a pincode/location.

    Returns ``(serviceable: bool, area: ServiceableArea | None)``.
    """
    if not _enforced():
        return True, None
    # Not configured yet → serve everywhere.
    if not ServiceableArea.objects.filter(is_active=True).exists():
        return True, None

    area = area_for_pincode(pincode)
    if not area:
        return False, None

    if area.has_geofence and lat is not None and lng is not None:
        distance = haversine_km(area.center_lat, area.center_lng, lat, lng)
        if distance > float(area.radius_km):
            return False, area

    return True, area


def is_serviceable(address):
    """True if ``address`` can be delivered to."""
    serviceable, _ = check(
        getattr(address, "pincode", None),
        getattr(address, "latitude", None),
        getattr(address, "longitude", None),
    )
    return serviceable
