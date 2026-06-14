from django.contrib import admin

from .models import FAQ, OrderReview, ProductRating, SupportTicket, TicketMessage


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "topic", "is_active", "sort_order")
    list_filter = ("topic", "is_active")
    search_fields = ("question", "answer")


@admin.register(OrderReview)
class OrderReviewAdmin(admin.ModelAdmin):
    list_display = ("order", "user", "order_rating", "rider_rating", "created_at")
    list_filter = ("order_rating", "rider_rating")
    search_fields = ("order__order_number", "user__phone")
    readonly_fields = ("created_at",)


@admin.register(ProductRating)
class ProductRatingAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("product__name", "user__phone")
    readonly_fields = ("created_at",)


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_number", "user", "reason", "status", "resolution_type", "created_at")
    list_filter = ("status", "reason", "resolution_type")
    search_fields = ("ticket_number", "user__phone", "order__order_number")
    readonly_fields = ("ticket_number", "created_at", "updated_at", "resolved_at")
    inlines = [TicketMessageInline]
    actions = ["mark_in_progress", "resolve_with_replacement"]

    @admin.action(description="Mark selected tickets as in progress")
    def mark_in_progress(self, request, queryset):
        queryset.update(status=SupportTicket.Status.IN_PROGRESS)

    @admin.action(description="Resolve selected tickets with a replacement")
    def resolve_with_replacement(self, request, queryset):
        from .services import resolve_ticket

        resolved = 0
        for ticket in queryset.exclude(status=SupportTicket.Status.RESOLVED):
            resolve_ticket(
                ticket,
                resolution_type=SupportTicket.Resolution.REPLACEMENT,
                note="Replacement arranged via admin.",
            )
            resolved += 1
        self.message_user(request, f"Resolved {resolved} ticket(s) with a replacement.")
