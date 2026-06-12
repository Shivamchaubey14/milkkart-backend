from django_filters import rest_framework as filters

from .models import Product


class ProductFilter(filters.FilterSet):
    category = filters.NumberFilter(field_name="category_id")
    category_slug = filters.CharFilter(field_name="category__slug")
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = ["category", "category_slug", "min_price", "max_price", "in_stock"]

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock__gt=0)
        return queryset.filter(stock=0)
