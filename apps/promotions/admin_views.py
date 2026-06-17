"""Coupon and banner management for the ops/admin panel (FR-ADM-02)."""

from rest_framework import generics

from apps.core.permissions import IsOpsManager

from .admin_serializers import AdminBannerSerializer, AdminCouponSerializer
from .models import Banner, Coupon


class AdminCouponList(generics.ListCreateAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminCouponSerializer
    pagination_class = None
    queryset = Coupon.objects.all()


class AdminCouponDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminCouponSerializer
    queryset = Coupon.objects.all()


class AdminBannerList(generics.ListCreateAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminBannerSerializer
    pagination_class = None
    queryset = Banner.objects.all()


class AdminBannerDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOpsManager]
    serializer_class = AdminBannerSerializer
    queryset = Banner.objects.all()
