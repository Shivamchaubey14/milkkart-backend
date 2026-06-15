import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsOpsManager

from . import services


def _resolve_range(request):
    """Return (start, end, error) dates from ?start/?end, defaulting to this month."""
    today = datetime.date.today()
    start_param = request.query_params.get("start")
    end_param = request.query_params.get("end")
    try:
        start = datetime.date.fromisoformat(start_param) if start_param else today.replace(day=1)
        end = datetime.date.fromisoformat(end_param) if end_param else today
    except ValueError:
        return None, None, "Invalid date — use YYYY-MM-DD."
    if end < start:
        return None, None, "'end' must not be before 'start'."
    return start, end, None


@api_view(["GET"])
@permission_classes([IsOpsManager])
def sales_summary(request):
    start, end, error = _resolve_range(request)
    if error:
        return Response({"error": error}, status=400)
    return Response(services.sales_summary(start, end))


@api_view(["GET"])
@permission_classes([IsOpsManager])
def top_products(request):
    start, end, error = _resolve_range(request)
    if error:
        return Response({"error": error}, status=400)
    raw_limit = request.query_params.get("limit")
    limit = int(raw_limit) if raw_limit and raw_limit.isdigit() else 10
    return Response(services.top_products(start, end, limit=limit))


@api_view(["GET"])
@permission_classes([IsOpsManager])
def order_status_breakdown(request):
    start, end, error = _resolve_range(request)
    if error:
        return Response({"error": error}, status=400)
    return Response(services.order_status_breakdown(start, end))


@api_view(["GET"])
@permission_classes([IsOpsManager])
def subscription_report(request):
    start, end, error = _resolve_range(request)
    if error:
        return Response({"error": error}, status=400)
    return Response(services.subscription_report(start, end))


@api_view(["GET"])
@permission_classes([IsOpsManager])
def rider_performance(request):
    start, end, error = _resolve_range(request)
    if error:
        return Response({"error": error}, status=400)
    return Response(services.rider_performance(start, end))
