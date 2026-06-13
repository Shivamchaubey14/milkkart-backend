from django.urls import path

from . import views

urlpatterns = [
    path("", views.wallet_detail, name="wallet-detail"),
    path("transactions/", views.WalletTransactionListView.as_view(), name="wallet-transactions"),
    path("topup/", views.wallet_topup, name="wallet-topup"),
    path("topup/verify/", views.wallet_topup_verify, name="wallet-topup-verify"),
]
