from django.urls import path

from . import views

urlpatterns = [
    path("duty/", views.rider_duty, name="rider-duty"),
    path("location/", views.rider_location, name="rider-location"),
    path("assignments/", views.rider_assignments, name="rider-assignments"),
    path("day/", views.rider_day, name="rider-day"),
    path("deliveries/", views.rider_deliveries, name="rider-deliveries"),
    path("orders/<uuid:order_number>/accept/", views.accept_order, name="rider-accept"),
    path("orders/<uuid:order_number>/pickup/", views.pickup_order, name="rider-pickup"),
    path("orders/<uuid:order_number>/deliver/", views.deliver_order, name="rider-deliver"),
    path("orders/<uuid:order_number>/return/", views.return_order, name="rider-return"),
]
