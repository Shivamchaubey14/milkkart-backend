"""Ops view of delivery partners — duty, current load and location — for the
order board's rider assignment picker. Guarded by the ops/admin role.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsOpsManager

from .services import riders_with_load


@api_view(["GET"])
@permission_classes([IsOpsManager])
def riders_board(request):
    riders = riders_with_load()
    return Response([
        {
            "id": r.id,
            "phone": r.user.phone,
            "name": r.user.name,
            "vehicle_number": r.vehicle_number,
            "is_on_duty": r.is_on_duty,
            "load": r.load,
            "current_lat": str(r.current_lat) if r.current_lat is not None else None,
            "current_lng": str(r.current_lng) if r.current_lng is not None else None,
        }
        for r in riders
    ])
