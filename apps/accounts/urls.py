from django.urls import path

from . import views

urlpatterns = [
    path("otp/send/", views.send_otp, name="otp-send"),
    path("otp/verify/", views.verify_otp, name="otp-verify"),
    path("me/", views.me, name="user-me"),
]
