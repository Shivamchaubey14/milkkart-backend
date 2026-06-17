"""Subscription ops dashboard (FR-ADM-05): next-morning demand forecast and the
per-stop route sheet for riders. Guarded by the ops/admin role.
"""

import datetime

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsOpsManager

from . import services


@api_view(["GET"])
@permission_classes([IsOpsManager])
def forecast(request):
    date_param = request.query_params.get("date")
    if date_param:
        try:
            date = datetime.date.fromisoformat(date_param)
        except ValueError:
            return Response({"error": "Invalid date — use YYYY-MM-DD."}, status=400)
    else:
        date = timezone.localdate() + datetime.timedelta(days=1)
    return Response(services.demand_forecast(date))
