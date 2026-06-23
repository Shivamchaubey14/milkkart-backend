from django.urls import path

from . import views

urlpatterns = [
    path("", views.wallet_detail, name="wallet-detail"),
    path("transactions/", views.WalletTransactionListView.as_view(), name="wallet-transactions"),
    path("topup/", views.wallet_topup, name="wallet-topup"),
    path("topup/verify/", views.wallet_topup_verify, name="wallet-topup-verify"),
    path("topup/mock-pay/", views.wallet_topup_mock_pay, name="wallet-topup-mock-pay"),
    path("topup/<int:pk>/status/", views.wallet_topup_status, name="wallet-topup-status"),
]
