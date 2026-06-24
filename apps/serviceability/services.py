"""Serviceability checks: can we deliver to a pincode / location?

The model is fail-open *until configured*: with no active areas in the table at
all, everywhere is serviceable (geofencing not yet set up). Once any area exists,
only matching pincodes (and, where set, points inside the geofence) are served.
``SERVICEABILITY_ENFORCED=False`` disables the gate entirely.
"""

import math

from django.conf import settings

from .models import DeliveryZone, ServiceableArea


def _enforced():
    return getattr(settings, "SERVICEABILITY_ENFORCED", True)


# ── Point-in-polygon (GeoJSON, no PostGIS) ──────────────────────────────────
# GeoJSON coordinates are [lng, lat]; the ray-cast below uses x=lng, y=lat.


def _point_in_ring(x, y, ring):
    """Ray-casting test: is (x, y) inside the linear ring (list of [lng, lat])?"""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_polygon(x, y, polygon):
    """polygon = [outer_ring, hole1, …]. Inside outer and outside every hole."""
    if not polygon:
        return False
    if not _point_in_ring(x, y, polygon[0]):
        return False
    return not any(_point_in_ring(x, y, hole) for hole in polygon[1:])


def point_in_geometry(lat, lng, geometry):
    """True if (lat, lng) falls inside a GeoJSON Polygon / MultiPolygon."""
    if not geometry:
        return False
    try:
        x, y = float(lng), float(lat)
    except (TypeError, ValueError):
        return False
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if geom_type == "Polygon":
        return _point_in_polygon(x, y, coords)
    if geom_type == "MultiPolygon":
        return any(_point_in_polygon(x, y, poly) for poly in coords)
    return False


def zone_for_point(lat, lng):
    """Highest-priority active DeliveryZone whose polygon contains the point."""
    if lat is None or lng is None:
        return None
    for zone in DeliveryZone.objects.filter(is_active=True).order_by("-priority", "id"):
        if point_in_geometry(lat, lng, zone.polygon):
            return zone
    return None


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

    Returns ``(serviceable: bool, area: DeliveryZone | ServiceableArea | None)``.
    A point inside a drawn DeliveryZone is serviceable (precise geofence); a
    matching pincode ServiceableArea is the coarse fallback. Both are unioned so
    coarse geocoding never wrongly rejects a real pincode match.
    """
    if not _enforced():
        return True, None

    has_zones = DeliveryZone.objects.filter(is_active=True).exists()
    has_areas = ServiceableArea.objects.filter(is_active=True).exists()
    # Not configured yet → serve everywhere.
    if not has_zones and not has_areas:
        return True, None

    # Drawn polygon zones first (precise, when we have coordinates).
    zone = zone_for_point(lat, lng)
    if zone:
        return True, zone

    # Pincode fallback.
    area = area_for_pincode(pincode)
    if area:
        if area.has_geofence and lat is not None and lng is not None:
            distance = haversine_km(area.center_lat, area.center_lng, lat, lng)
            if distance > float(area.radius_km):
                return False, area
        return True, area

    return False, None


def is_serviceable(address):
    """True if ``address`` can be delivered to."""
    serviceable, _ = check(
        getattr(address, "pincode", None),
        getattr(address, "latitude", None),
        getattr(address, "longitude", None),
    )
    return serviceable
