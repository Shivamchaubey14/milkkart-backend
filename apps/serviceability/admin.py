from django.contrib import admin

from .models import DeliveryZone, ServiceableArea, WaitlistEntry


@admin.register(ServiceableArea)
class ServiceableAreaAdmin(admin.ModelAdmin):
    list_display = ("pincode", "area_name", "city", "is_active", "delivery_eta_minutes")
    list_filter = ("is_active", "city")
    search_fields = ("pincode", "area_name", "city")


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "is_active", "priority", "delivery_eta_minutes")
    list_filter = ("is_active", "city")
    search_fields = ("name", "city", "state")


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = ("phone", "pincode", "city", "notified", "created_at")
    list_filter = ("notified", "pincode", "city")
    search_fields = ("phone", "pincode", "city")
    readonly_fields = ("created_at", "updated_at")
