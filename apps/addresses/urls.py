from django.urls import path

from . import views

urlpatterns = [
    path("", views.address_list_create, name="address-list-create"),
    path("<int:address_id>/", views.address_detail, name="address-detail"),
]
