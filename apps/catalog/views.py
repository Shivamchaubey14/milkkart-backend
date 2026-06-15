from django.db.models import Count, Min, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .cache import get_cached, set_cached
from .filters import ProductFilter
from .models import Category, Product
from .serializers import CategorySerializer, ProductDetailSerializer, ProductListSerializer


class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer

    def get_queryset(self):
        return (
            Category.objects.filter(is_active=True)
            .annotate(product_count=Count("products", distinct=True))
        )

    def list(self, request, *args, **kwargs):
        suffix = f"categories:{request.get_full_path()}"
        cached = get_cached(suffix)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        set_cached(suffix, response.data)
        return response


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "description", "brand", "tags"]
    ordering_fields = ["min_price", "created_at", "name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Product.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related("variants", "images")
            .annotate(min_price=Min("variants__price", filter=Q(variants__is_active=True)))
            .distinct()
        )

    def list(self, request, *args, **kwargs):
        # Key on the full path so each filter/search/sort/page combination is cached.
        suffix = f"products:{request.get_full_path()}"
        cached = get_cached(suffix)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        set_cached(suffix, response.data)
        return response


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Product.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related("variants", "images")
        )

    def retrieve(self, request, *args, **kwargs):
        suffix = f"product:{kwargs['slug']}"
        cached = get_cached(suffix)
        if cached is not None:
            return Response(cached)
        response = super().retrieve(request, *args, **kwargs)
        set_cached(suffix, response.data)
        return response
