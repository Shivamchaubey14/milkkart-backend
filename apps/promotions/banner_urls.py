from django.urls import path

from . import views

urlpatterns = [
    path("", views.banner_list, name="banner-list"),
]
