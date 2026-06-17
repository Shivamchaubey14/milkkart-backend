"""Ops view of delivery partners — duty, current load and location — for the
order board's rider assignment picker, plus rider onboarding. Guarded by the
ops/admin role.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.models import User, phone_validator
from apps.core.permissions import IsOpsManager

from .models import DeliveryPartner
from .services import riders_with_load


def _serialize(rider, load=0):
    return {
        "id": rider.id,
        "phone": rider.user.phone,
        "name": rider.user.name,
        "email": rider.user.email,
        "address": rider.user.address,
        "vehicle_number": rider.vehicle_number,
        "is_on_duty": rider.is_on_duty,
        "is_active": rider.is_active,
        "load": load,
        "current_lat": str(rider.current_lat) if rider.current_lat is not None else None,
        "current_lng": str(rider.current_lng) if rider.current_lng is not None else None,
    }


@api_view(["GET", "POST"])
@permission_classes([IsOpsManager])
def riders_board(request):
    if request.method == "POST":
        return _create_rider(request)
    riders = riders_with_load()
    return Response([_serialize(r, r.load) for r in riders])


def _create_rider(request):
    """Onboard a delivery partner: find-or-create the user by phone, fill in
    their profile, and attach a DeliveryPartner profile."""
    data = request.data
    phone = (data.get("phone") or "").strip()
    if not phone:
        return Response({"error": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        phone_validator(phone)
    except Exception:
        return Response(
            {"error": "Phone number must be 9-15 digits, optionally starting with '+'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user, _ = User.objects.get_or_create(phone=phone)
    # Fill in any profile fields the operator provided (don't blank existing ones).
    profile_changed = []
    for field in ("name", "email", "address"):
        value = data.get(field)
        if value is not None and str(value).strip():
            setattr(user, field, str(value).strip())
            profile_changed.append(field)
    if profile_changed:
        user.save(update_fields=profile_changed)

    if hasattr(user, "delivery_partner"):
        return Response(
            {"error": "This person is already a rider."},
            status=status.HTTP_409_CONFLICT,
        )

    rider = DeliveryPartner.objects.create(
        user=user,
        vehicle_number=(data.get("vehicle_number") or "").strip(),
    )
    return Response(_serialize(rider), status=status.HTTP_201_CREATED)
