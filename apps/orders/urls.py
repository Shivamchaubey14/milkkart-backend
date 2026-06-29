from django.urls import path

from . import views

urlpatterns = [
    path("checkout/", views.checkout, name="order-checkout"),
    path("window/", views.order_window, name="order-window"),
    path("", views.order_list, name="order-list"),
    path("<uuid:order_number>/", views.order_detail, name="order-detail"),
    path("<uuid:order_number>/cancel/", views.cancel_order, name="order-cancel"),
    path("delivery-slots/", views.delivery_slot_list, name="delivery-slot-list"),
]
