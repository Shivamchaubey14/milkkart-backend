from django.urls import path

from . import views

urlpatterns = [
    path("checkout/", views.checkout, name="order-checkout"),
    path("", views.order_list, name="order-list"),
    path("<uuid:order_number>/", views.order_detail, name="order-detail"),
]
