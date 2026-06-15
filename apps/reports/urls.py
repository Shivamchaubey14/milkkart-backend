from django.urls import path

from . import views

urlpatterns = [
    path("sales/", views.sales_summary, name="report-sales"),
    path("top-products/", views.top_products, name="report-top-products"),
    path("order-status/", views.order_status_breakdown, name="report-order-status"),
    path("subscriptions/", views.subscription_report, name="report-subscriptions"),
    path("riders/", views.rider_performance, name="report-riders"),
]
