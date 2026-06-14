from django.urls import path

from . import views

urlpatterns = [
    path("faqs/", views.FAQListView.as_view(), name="faq-list"),
    path(
        "orders/<uuid:order_number>/rating/",
        views.order_rating,
        name="order-rating",
    ),
    path(
        "products/<int:product_id>/rating/",
        views.product_rating,
        name="product-rating",
    ),
    path("tickets/", views.SupportTicketListCreateView.as_view(), name="ticket-list"),
    path(
        "tickets/<uuid:ticket_number>/",
        views.SupportTicketDetailView.as_view(),
        name="ticket-detail",
    ),
    path(
        "tickets/<uuid:ticket_number>/messages/",
        views.add_ticket_message,
        name="ticket-message",
    ),
    path(
        "tickets/<uuid:ticket_number>/resolve/",
        views.resolve_ticket,
        name="ticket-resolve",
    ),
]
