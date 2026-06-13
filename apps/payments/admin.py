from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_id", "order", "user", "method", "status", "amount", "created_at")
    list_filter = ("status", "method", "created_at")
    search_fields = ("payment_id", "gateway_order_id", "gateway_payment_id", "user__phone")
    readonly_fields = (
        "payment_id",
        "gateway_order_id",
        "gateway_payment_id",
        "gateway_signature",
        "created_at",
        "updated_at",
    )
