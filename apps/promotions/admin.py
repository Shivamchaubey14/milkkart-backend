from django.contrib import admin

from .models import Banner, Coupon, CouponRedemption


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "subtitle", "is_active", "sort_order", "link_url")
    list_filter = ("is_active",)
    list_editable = ("is_active", "sort_order")
    search_fields = ("title", "subtitle")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount_type",
        "value",
        "min_order_value",
        "times_used",
        "usage_limit",
        "valid_until",
        "is_active",
    )
    list_filter = ("discount_type", "is_active", "first_order_only")
    search_fields = ("code", "description")
    readonly_fields = ("times_used", "created_at", "updated_at")


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "discount_amount", "created_at")
    list_filter = ("coupon",)
    search_fields = ("coupon__code", "user__phone")
    readonly_fields = ("coupon", "user", "order", "discount_amount", "created_at")
