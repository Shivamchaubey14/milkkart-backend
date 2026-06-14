from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.permissions import IsOpsManager

from . import services
from .models import ServiceableArea
from .serializers import ServiceableAreaSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def check(request):
    """Public pre-checkout check: is a pincode (optionally a point) serviceable?"""
    pincode = request.query_params.get("pincode")
    lat = request.query_params.get("lat")
    lng = request.query_params.get("lng")
    if not pincode and not (lat and lng):
        return Response(
            {"error": "Provide a 'pincode' (and optionally 'lat'/'lng')."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        lat_val = float(lat) if lat else None
        lng_val = float(lng) if lng else None
    except ValueError:
        return Response({"error": "lat/lng must be numbers."}, status=status.HTTP_400_BAD_REQUEST)

    serviceable, area = services.check(pincode, lat_val, lng_val)
    return Response(
        {
            "serviceable": serviceable,
            "area": ServiceableAreaSerializer(area).data if area else None,
        }
    )


class ServiceableAreaListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = ServiceableAreaSerializer
    queryset = ServiceableArea.objects.all()


class ServiceableAreaDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = ServiceableAreaSerializer
    queryset = ServiceableArea.objects.all()
