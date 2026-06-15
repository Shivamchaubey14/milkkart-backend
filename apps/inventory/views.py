from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.catalog.models import ProductVariant
from apps.core.permissions import IsWarehouseStaff

from . import services
from .models import StockMovement
from .serializers import (
    AdjustStockSerializer,
    LowStockSerializer,
    RestockSerializer,
    StockMovementSerializer,
)


class StockMovementListView(generics.ListAPIView):
    permission_classes = [IsWarehouseStaff]
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        qs = StockMovement.objects.select_related(
            "variant__product", "order", "created_by"
        )
        variant_id = self.request.query_params.get("variant_id")
        if variant_id:
            qs = qs.filter(variant_id=variant_id)
        reason = self.request.query_params.get("reason")
        if reason:
            qs = qs.filter(reason=reason)
        return qs


def _get_variant(variant_id):
    return ProductVariant.objects.filter(pk=variant_id).first()


@api_view(["POST"])
@permission_classes([IsWarehouseStaff])
def restock(request):
    serializer = RestockSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    variant = _get_variant(serializer.validated_data["variant_id"])
    if not variant:
        return Response({"error": "Variant not found."}, status=status.HTTP_404_NOT_FOUND)

    movement = services.restock(
        variant,
        serializer.validated_data["quantity"],
        user=request.user,
        note=serializer.validated_data.get("note", ""),
    )
    return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsWarehouseStaff])
def adjust(request):
    """Manual correction or damage write-off."""
    serializer = AdjustStockSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    variant = _get_variant(serializer.validated_data["variant_id"])
    if not variant:
        return Response({"error": "Variant not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        movement = services.adjust_stock(
            variant,
            serializer.validated_data["delta"],
            serializer.validated_data["reason"],
            note=serializer.validated_data.get("note", ""),
            user=request.user,
        )
    except services.OutOfStock as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsWarehouseStaff])
def low_stock(request):
    from django.conf import settings

    raw = request.query_params.get("threshold")
    threshold = int(raw) if raw and raw.isdigit() else settings.LOW_STOCK_THRESHOLD
    variants = services.low_stock_variants(threshold)
    return Response(
        {
            "threshold": threshold,
            "count": variants.count(),
            "variants": LowStockSerializer(variants, many=True).data,
        }
    )
