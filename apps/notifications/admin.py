from django.contrib import admin

from .models import DeviceToken, Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "title", "is_read", "created_at")
    list_filter = ("category", "is_read")
    search_fields = ("user__phone", "title")
    readonly_fields = ("created_at", "read_at")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "push_enabled", "sms_enabled", "email_enabled", "promotions")
    search_fields = ("user__phone",)


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "is_active", "created_at")
    list_filter = ("platform", "is_active")
    search_fields = ("user__phone", "token")
