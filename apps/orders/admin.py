from django.contrib import admin

from .models import DeliverySlot, Order, OrderItem
from .tasks import send_order_status_update


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "variant_label", "product_price", "quantity")


def _make_status_action(new_status, description):
    def action(modeladmin, request, queryset):
        for order in queryset:
            order.status = new_status
            order.save(update_fields=["status"])
            send_order_status_update.delay(order.id, new_status)

    action.short_description = description
    action.__name__ = f"mark_{new_status}"
    return action


@admin.action(description="Auto-assign to an available rider")
def auto_assign_rider(modeladmin, request, queryset):
    from apps.delivery.services import NoRiderAvailable, assign_order

    assigned = 0
    for order in queryset:
        try:
            assign_order(order)
            assigned += 1
        except NoRiderAvailable:
            modeladmin.message_user(
                request, f"No rider available for {order.order_number}.", level="warning"
            )
    if assigned:
        modeladmin.message_user(request, f"Assigned {assigned} order(s) to riders.")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "status", "total", "placed_at")
    list_filter = ("status", "placed_at")
    search_fields = ("order_number", "user__phone")
    readonly_fields = ("order_number", "placed_at")
    inlines = [OrderItemInline]
    actions = [
        auto_assign_rider,
        _make_status_action("confirmed", "Mark as Confirmed"),
        _make_status_action("out_for_delivery", "Mark as Out for Delivery"),
        _make_status_action("delivered", "Mark as Delivered"),
        _make_status_action("cancelled", "Mark as Cancelled"),
    ]


@admin.register(DeliverySlot)
class DeliverySlotAdmin(admin.ModelAdmin):
    list_display = ("date", "start_time", "end_time", "capacity", "booked", "available")
    list_filter = ("date",)
