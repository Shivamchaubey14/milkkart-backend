from django.contrib import admin

from .models import Payment, PaymentWebhookEvent


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


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed", "created_at")
    list_filter = ("event_type", "processed")
    search_fields = ("event_id", "event_type")
    readonly_fields = ("event_id", "event_type", "payload", "processed", "created_at")

    def has_add_permission(self, request):
        return False
