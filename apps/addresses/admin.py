from django.contrib import admin

from .models import Address


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "address_line", "city", "pincode", "is_default")
    list_filter = ("label", "city", "is_default")
    search_fields = ("address_line", "city", "pincode", "user__phone")
