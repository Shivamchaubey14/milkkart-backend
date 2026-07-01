from django.urls import path

from . import admin_views

urlpatterns = [
    path("riders/", admin_views.riders_board, name="admin-riders-board"),
    path("riders/<int:pk>/", admin_views.rider_detail, name="admin-rider-detail"),
]
