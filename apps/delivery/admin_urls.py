from django.urls import path

from . import admin_views

urlpatterns = [
    path("riders/", admin_views.riders_board, name="admin-riders-board"),
]
