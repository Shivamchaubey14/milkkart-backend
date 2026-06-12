from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "product_price", "quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "status", "total", "placed_at")
    list_filter = ("status", "placed_at")
    search_fields = ("order_number", "user__phone")
    readonly_fields = ("order_number", "placed_at")
    inlines = [OrderItemInline]
