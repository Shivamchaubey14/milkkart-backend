from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .admin_serializers import StoreConfigSerializer
from .models import StoreConfig
from .permissions import IsAdminRole


@api_view(["GET", "PUT"])
@permission_classes([IsAdminRole])
def store_settings(request):
    """Get or update the storefront config (fees + next-day ordering window).

    Single-row config (``StoreConfig.get_solo``); PUT accepts a partial body so
    the admin can save just the ordering-window fields without resending fees.
    """
    config = StoreConfig.get_solo()
    if request.method == "PUT":
        serializer = StoreConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        data = serializer.data
    else:
        data = StoreConfigSerializer(config).data
    response = Response(data)
    # The admin must always read back the live values, never a cached copy.
    response["Cache-Control"] = "no-store"
    return response
