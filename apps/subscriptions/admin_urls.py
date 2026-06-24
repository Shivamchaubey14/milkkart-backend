from django.urls import path

from . import admin_views

urlpatterns = [
    path("forecast/", admin_views.forecast, name="admin-subscription-forecast"),
    path("vacations/", admin_views.vacations, name="admin-subscription-vacations"),
]
