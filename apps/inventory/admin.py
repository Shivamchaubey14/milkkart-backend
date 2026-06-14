from django.contrib import admin

from .models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("variant", "delta", "reason", "balance_after", "created_by", "created_at")
    list_filter = ("reason",)
    search_fields = ("variant__sku", "variant__product__name", "note")
    readonly_fields = ("variant", "delta", "reason", "balance_after", "order", "created_by", "created_at")

    def has_add_permission(self, request):
        # Movements are written by the inventory service, never by hand.
        return False
