from django.urls import path

from . import views

urlpatterns = [
    path("initiate/", views.initiate_payment, name="payment-initiate"),
    path("verify/", views.verify_payment, name="payment-verify"),
    path("<uuid:order_number>/", views.payment_detail, name="payment-detail"),
]
