from django.urls import path

from . import views

urlpatterns = [
    path("", views.cart_detail, name="cart-detail"),
    path("add/", views.add_to_cart, name="cart-add"),
    path("items/<int:item_id>/", views.cart_item_detail, name="cart-item-detail"),
]
