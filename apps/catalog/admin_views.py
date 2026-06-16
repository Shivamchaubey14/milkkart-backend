"""Catalog management endpoints for the ops/admin panel (FR-ADM-02).

CRUD for categories, products and variants. The catalog cache is invalidated
automatically by the post_save/post_delete signals on these models.
"""

from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404

from apps.core.permissions import IsOpsManager

from .admin_serializers import AdminCategorySerializer, AdminProductSerializer, AdminVariantSerializer
from .models import Category, Product, ProductVariant


class AdminCategoryList(generics.ListCreateAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminCategorySerializer
    pagination_class = None
    queryset = Category.objects.all()


class AdminCategoryDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminCategorySerializer
    queryset = Category.objects.all()

    def perform_destroy(self, instance):
        if instance.products.exists():
            raise ValidationError("Category still has products — deactivate it or move its products first.")
        instance.delete()


class AdminProductList(generics.ListCreateAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminProductSerializer
    pagination_class = None

    def get_queryset(self):
        return Product.objects.select_related("category").prefetch_related("variants").order_by("name")


class AdminProductDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminProductSerializer

    def get_queryset(self):
        return Product.objects.select_related("category").prefetch_related("variants")


class AdminVariantCreate(generics.CreateAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminVariantSerializer

    def perform_create(self, serializer):
        product = get_object_or_404(Product, pk=self.kwargs["product_id"])
        serializer.save(product=product)


class AdminVariantDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminVariantSerializer
    queryset = ProductVariant.objects.all()
