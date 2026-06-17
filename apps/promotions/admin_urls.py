from django.urls import path

from . import admin_views

urlpatterns = [
    path("coupons/", admin_views.AdminCouponList.as_view(), name="admin-coupon-list"),
    path("coupons/<int:pk>/", admin_views.AdminCouponDetail.as_view(), name="admin-coupon-detail"),
    path("banners/", admin_views.AdminBannerList.as_view(), name="admin-banner-list"),
    path("banners/<int:pk>/", admin_views.AdminBannerDetail.as_view(), name="admin-banner-detail"),
]
