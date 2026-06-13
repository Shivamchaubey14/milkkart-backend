from django.urls import path

from . import views

urlpatterns = [
    path("duty/", views.rider_duty, name="rider-duty"),
    path("location/", views.rider_location, name="rider-location"),
    path("assignments/", views.rider_assignments, name="rider-assignments"),
    path("orders/<uuid:order_number>/accept/", views.accept_order, name="rider-accept"),
    path("orders/<uuid:order_number>/pickup/", views.pickup_order, name="rider-pickup"),
    path("orders/<uuid:order_number>/deliver/", views.deliver_order, name="rider-deliver"),
]
