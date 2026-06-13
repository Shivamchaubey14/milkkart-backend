from django.urls import path

from . import views

urlpatterns = [
    path("", views.coupon_list, name="coupon-list"),
]
