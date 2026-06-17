import logging

from celery import shared_task

from .models import Address
from .services import coordinates_for

logger = logging.getLogger(__name__)


@shared_task
def geocode_address(address_id):
    """Fill in an address's latitude/longitude from its text, if still missing.

    Runs async in prod (eager/inline in dev). Lets live order tracking draw a
    real road route to the address without relying on client-side geocoding.
    """
    try:
        address = Address.objects.get(pk=address_id)
    except Address.DoesNotExist:
        return {"address_id": address_id, "status": "missing"}

    if address.latitude is not None and address.longitude is not None:
        return {"address_id": address_id, "status": "already_set"}

    coords = coordinates_for(address)
    if not coords:
        return {"address_id": address_id, "status": "not_found"}

    address.latitude, address.longitude = coords
    address.save(update_fields=["latitude", "longitude", "updated_at"])
    return {"address_id": address_id, "status": "geocoded", "lat": str(coords[0]), "lng": str(coords[1])}
