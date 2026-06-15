from django.contrib import admin

from .models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "order", "total", "issued_at", "emailed_at")
    search_fields = ("number", "order__order_number")
    readonly_fields = ("number", "issued_at", "emailed_at")
