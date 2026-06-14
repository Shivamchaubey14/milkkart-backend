from django.urls import path

from . import views

urlpatterns = [
    path("", views.InvoiceListView.as_view(), name="invoice-list"),
    path("statement/", views.statement, name="invoice-statement"),
    path("<uuid:order_number>/", views.invoice_for_order, name="invoice-for-order"),
    path("<uuid:order_number>/email/", views.email_invoice_view, name="invoice-email"),
]
