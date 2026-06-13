from django.contrib import admin

from .models import Wallet, WalletTopup, WalletTransaction


class WalletTransactionInline(admin.TabularInline):
    model = WalletTransaction
    extra = 0
    readonly_fields = ("type", "amount", "balance_after", "order", "description", "created_at")
    can_delete = False


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "updated_at")
    search_fields = ("user__phone",)
    readonly_fields = ("balance", "created_at", "updated_at")
    inlines = [WalletTransactionInline]


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "type", "amount", "balance_after", "order", "created_at")
    list_filter = ("type",)
    search_fields = ("wallet__user__phone",)
    readonly_fields = ("wallet", "type", "amount", "balance_after", "order", "description", "created_at")


@admin.register(WalletTopup)
class WalletTopupAdmin(admin.ModelAdmin):
    list_display = ("wallet", "amount", "status", "gateway_order_id", "created_at")
    list_filter = ("status",)
    search_fields = ("wallet__user__phone", "gateway_order_id")
    readonly_fields = ("wallet", "amount", "gateway_order_id", "gateway_payment_id", "created_at", "updated_at")
