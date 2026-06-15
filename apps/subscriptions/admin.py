from django.contrib import admin

from .models import Subscription, SubscriptionDelivery, SubscriptionVacation


class SubscriptionVacationInline(admin.TabularInline):
    model = SubscriptionVacation
    extra = 0


class SubscriptionDeliveryInline(admin.TabularInline):
    model = SubscriptionDelivery
    extra = 0
    readonly_fields = ("date", "quantity", "amount", "status", "order")
    can_delete = False
    ordering = ("-date",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "variant", "quantity", "frequency", "status", "start_date")
    list_filter = ("status", "frequency")
    search_fields = ("user__phone", "user__name", "variant__sku")
    raw_id_fields = ("user", "variant", "address")
    inlines = [SubscriptionVacationInline, SubscriptionDeliveryInline]


@admin.register(SubscriptionDelivery)
class SubscriptionDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "subscription", "date", "quantity", "amount", "status", "order")
    list_filter = ("status", "date")
    search_fields = ("subscription__user__phone",)
    raw_id_fields = ("subscription", "order")
