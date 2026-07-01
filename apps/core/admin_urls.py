from django.urls import path

from . import admin_views

urlpatterns = [
    path("settings/", admin_views.store_settings, name="admin-store-settings"),
]
