from django.urls import path

from . import views

urlpatterns = [
    path("movements/", views.StockMovementListView.as_view(), name="stock-movement-list"),
    path("restock/", views.restock, name="stock-restock"),
    path("adjust/", views.adjust, name="stock-adjust"),
    path("low-stock/", views.low_stock, name="low-stock"),
]
