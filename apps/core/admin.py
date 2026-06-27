from django.contrib import admin

from .models import StoreConfig


@admin.register(StoreConfig)
class StoreConfigAdmin(admin.ModelAdmin):
    """Single-row config: edit the storefront fees, no add/delete."""

    list_display = (
        "free_delivery_threshold",
        "delivery_fee",
        "small_cart_threshold",
        "small_cart_fee",
        "tax_percent",
        "updated_at",
    )

    def has_add_permission(self, request):
        # Only ever one config row — block adding more.
        return not StoreConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
