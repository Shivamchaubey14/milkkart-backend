from django.db.models import Count, Q

from .models import DeliveryAssignment, DeliveryPartner

ACTIVE_STATUSES = [
    DeliveryAssignment.Status.ASSIGNED,
    DeliveryAssignment.Status.ACCEPTED,
    DeliveryAssignment.Status.PICKED_UP,
]


class NoRiderAvailable(Exception):
    """Raised when no on-duty rider is available for auto-assignment."""


def available_riders():
    return DeliveryPartner.objects.filter(is_active=True, is_on_duty=True)


def assign_order(order, rider=None):
    """Assign an order to a rider. Auto-picks the least-loaded on-duty rider if none given."""
    existing = DeliveryAssignment.objects.filter(order=order).first()
    if existing and existing.is_active:
        return existing

    if rider is None:
        rider = (
            available_riders()
            .annotate(active_load=Count("assignments", filter=Q(assignments__status__in=ACTIVE_STATUSES)))
            .order_by("active_load", "id")
            .first()
        )
        if rider is None:
            raise NoRiderAvailable("No on-duty rider available.")

    return DeliveryAssignment.objects.create(order=order, rider=rider)
