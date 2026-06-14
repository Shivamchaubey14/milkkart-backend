from django.urls import path

from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("unread-count/", views.unread_count, name="notification-unread-count"),
    path("read-all/", views.mark_all_read, name="notification-read-all"),
    path("preferences/", views.preferences, name="notification-preferences"),
    path("devices/", views.register_device, name="notification-register-device"),
    path("<int:pk>/read/", views.mark_read, name="notification-read"),
]
