from django.core.cache import cache
from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Liveness: the process is up and serving."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def readiness_check(request):
    """Readiness: the process can reach its dependencies (database and cache).

    Returns 200 only when every dependency responds; otherwise 503 with per-check
    status so a load balancer can pull the instance out of rotation.
    """
    checks = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    try:
        cache.set("readiness:ping", "1", 5)
        checks["cache"] = "ok" if cache.get("readiness:ping") == "1" else "error"
    except Exception:
        checks["cache"] = "error"

    healthy = all(value == "ok" for value in checks.values())
    code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response({"status": "ready" if healthy else "not_ready", "checks": checks}, status=code)
