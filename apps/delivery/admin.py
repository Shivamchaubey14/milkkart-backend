from django.contrib import admin

from .models import DeliveryAssignment, DeliveryPartner


@admin.register(DeliveryPartner)
class DeliveryPartnerAdmin(admin.ModelAdmin):
    list_display = ("user", "vehicle_number", "is_on_duty", "is_active", "last_location_at")
    list_filter = ("is_on_duty", "is_active")
    search_fields = ("user__phone", "vehicle_number")


@admin.register(DeliveryAssignment)
class DeliveryAssignmentAdmin(admin.ModelAdmin):
    list_display = ("order", "rider", "status", "assigned_at", "delivered_at")
    list_filter = ("status",)
    search_fields = ("order__order_number", "rider__user__phone")
    readonly_fields = ("delivery_otp", "assigned_at", "accepted_at", "picked_up_at", "delivered_at")
