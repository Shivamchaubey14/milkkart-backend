"""Subscription ops dashboard (FR-ADM-05): next-morning demand forecast and the
per-stop route sheet for riders. Guarded by the ops/admin role.
"""

import datetime

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsOpsManager

from . import services
from .models import Subscription, SubscriptionVacation


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


@api_view(["GET"])
@permission_classes([IsOpsManager])
def vacations(request):
    """Active and upcoming subscription vacations, so ops can see who has paused
    deliveries over which dates (no generation happens for those days)."""
    today = timezone.localdate()
    qs = (
        SubscriptionVacation.objects.filter(
            end_date__gte=today,
            subscription__status__in=[Subscription.Status.ACTIVE, Subscription.Status.PAUSED],
        )
        .select_related("subscription__user", "subscription__variant__product")
        .order_by("start_date", "end_date")
    )
    items = []
    for v in qs:
        sub = v.subscription
        items.append(
            {
                "subscription_id": sub.id,
                "vacation_id": v.id,
                "customer_name": sub.user.name or "",
                "customer_phone": sub.user.phone,
                "product": sub.variant.product.name,
                "label": sub.variant.label,
                "start_date": v.start_date.isoformat(),
                "end_date": v.end_date.isoformat(),
                "active": v.start_date <= today <= v.end_date,
            }
        )
    return Response({"date": today.isoformat(), "count": len(items), "vacations": items})
