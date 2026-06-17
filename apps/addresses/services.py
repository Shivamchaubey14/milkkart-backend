"""Address geocoding via OpenStreetMap Nominatim (no API key).

Best-effort: failures return None and never raise into the request path. Tries
the full address first, then progressively coarser queries (city + pincode,
then pincode) so a messy address line still resolves to roughly the right spot.
"""

import json
import logging
import urllib.parse
import urllib.request
from decimal import Decimal

logger = logging.getLogger(__name__)

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "MilkKart/1.0 (delivery address geocoding)"}


def geocode(query):
    """Return (Decimal lat, Decimal lng) for a free-text query, or None."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        url = _NOMINATIM + "?format=json&limit=1&q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.load(resp)
        if data:
            return (
                Decimal(str(round(float(data[0]["lat"]), 6))),
                Decimal(str(round(float(data[0]["lon"]), 6))),
            )
    except Exception:
        logger.warning("Geocoding failed for %r", query, exc_info=False)
    return None


def coordinates_for(address):
    """Geocode an Address, trying full → city+pincode → pincode. Returns coords or None."""
    full = ", ".join(
        p for p in [address.address_line, address.landmark, address.city, address.state, address.pincode] if p
    )
    city_pin = ", ".join(p for p in [address.city, address.state, address.pincode] if p)
    queries = [full]
    if city_pin:
        queries.append(city_pin + ", India")
    if address.pincode:
        queries.append(address.pincode + ", India")
    for q in queries:
        coords = geocode(q)
        if coords:
            return coords
    return None
