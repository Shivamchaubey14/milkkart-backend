from django.urls import path

from . import admin_views

urlpatterns = [
    path("categories/", admin_views.AdminCategoryList.as_view(), name="admin-category-list"),
    path("categories/<int:pk>/", admin_views.AdminCategoryDetail.as_view(), name="admin-category-detail"),
    path("products/", admin_views.AdminProductList.as_view(), name="admin-product-list"),
    path("products/<int:pk>/", admin_views.AdminProductDetail.as_view(), name="admin-product-detail"),
    path("products/<int:product_id>/variants/", admin_views.AdminVariantCreate.as_view(), name="admin-variant-create"),
    path("variants/<int:pk>/", admin_views.AdminVariantDetail.as_view(), name="admin-variant-detail"),
]
