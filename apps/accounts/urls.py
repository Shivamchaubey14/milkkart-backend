from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("otp/send/", views.send_otp, name="otp-send"),
    path("otp/verify/", views.verify_otp, name="otp-verify"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", views.me, name="user-me"),
]
