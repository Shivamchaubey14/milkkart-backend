from django.urls import path

from . import admin_views

urlpatterns = [
    path("", admin_views.order_board, name="admin-order-board"),
    path("<uuid:order_number>/confirm/", admin_views.confirm_order, name="admin-order-confirm"),
    path("<uuid:order_number>/cancel/", admin_views.cancel_order, name="admin-order-cancel"),
    path("<uuid:order_number>/assign/", admin_views.assign_rider, name="admin-order-assign"),
]
