from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.payments import gateway
from apps.wallet.models import (
    InsufficientBalance,
    Wallet,
    WalletTopup,
    WalletTransaction,
    get_or_create_wallet,
)

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+919876543210", name="Test User")


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def wallet(user):
    return get_or_create_wallet(user)


@pytest.mark.django_db
class TestWalletModel:
    def test_get_or_create_idempotent(self, user):
        w1 = get_or_create_wallet(user)
        w2 = get_or_create_wallet(user)
        assert w1.pk == w2.pk
        assert Wallet.objects.count() == 1

    def test_credit(self, wallet):
        txn = wallet.credit(Decimal("100"), WalletTransaction.Type.TOPUP)
        assert wallet.balance == Decimal("100.00")
        assert txn.balance_after == Decimal("100.00")
        assert txn.is_credit is True
        assert txn.signed_amount == Decimal("100.00")

    def test_debit(self, wallet):
        wallet.credit(Decimal("100"), WalletTransaction.Type.TOPUP)
        txn = wallet.debit(Decimal("30"), description="Order")
        assert wallet.balance == Decimal("70.00")
        assert txn.type == WalletTransaction.Type.DEBIT
        assert txn.is_credit is False
        assert txn.signed_amount == Decimal("-30.00")

    def test_debit_insufficient_raises(self, wallet):
        with pytest.raises(InsufficientBalance):
            wallet.debit(Decimal("50"))
        assert wallet.balance == Decimal("0.00")
        assert wallet.transactions.count() == 0

    def test_balance_after_tracks_running_balance(self, wallet):
        wallet.credit(Decimal("100"), WalletTransaction.Type.TOPUP)
        wallet.debit(Decimal("40"))
        wallet.credit(Decimal("10"), WalletTransaction.Type.CASHBACK)
        balances = list(wallet.transactions.order_by("created_at", "id").values_list("balance_after", flat=True))
        assert balances == [Decimal("100.00"), Decimal("60.00"), Decimal("70.00")]


@pytest.mark.django_db
class TestWalletAPI:
    def test_detail_empty(self, auth_client):
        response = auth_client.get(reverse("wallet-detail"))
        assert response.status_code == 200
        assert Decimal(response.data["balance"]) == Decimal("0.00")
        assert response.data["recent_transactions"] == []

    def test_detail_with_transactions(self, auth_client, wallet):
        wallet.credit(Decimal("100"), WalletTransaction.Type.TOPUP)
        response = auth_client.get(reverse("wallet-detail"))
        assert Decimal(response.data["balance"]) == Decimal("100.00")
        assert len(response.data["recent_transactions"]) == 1

    def test_transactions_list(self, auth_client, wallet):
        wallet.credit(Decimal("100"), WalletTransaction.Type.TOPUP)
        wallet.debit(Decimal("20"))
        response = auth_client.get(reverse("wallet-transactions"))
        assert response.status_code == 200
        assert len(response.data["results"]) == 2

    def test_requires_auth(self):
        response = APIClient().get(reverse("wallet-detail"))
        assert response.status_code == 401


@pytest.mark.django_db
class TestWalletTopup:
    def test_topup_creates_gateway_order(self, auth_client, user):
        response = auth_client.post(reverse("wallet-topup"), {"amount": "500"})
        assert response.status_code == 201
        assert response.data["gateway"]["order_id"].startswith("order_")
        assert response.data["gateway"]["amount"] == 50000  # paise
        topup = WalletTopup.objects.get(wallet__user=user)
        assert topup.status == WalletTopup.Status.CREATED

    def test_topup_verify_credits_wallet(self, auth_client, user):
        init = auth_client.post(reverse("wallet-topup"), {"amount": "500"})
        gw_order_id = init.data["gateway"]["order_id"]
        gw_payment_id = "pay_topup1"
        response = auth_client.post(
            reverse("wallet-topup-verify"),
            {
                "gateway_order_id": gw_order_id,
                "gateway_payment_id": gw_payment_id,
                "gateway_signature": gateway.sign(gw_order_id, gw_payment_id),
            },
        )
        assert response.status_code == 200
        assert Decimal(response.data["balance"]) == Decimal("500.00")
        topup = WalletTopup.objects.get(gateway_order_id=gw_order_id)
        assert topup.status == WalletTopup.Status.SUCCESS

    def test_topup_verify_bad_signature(self, auth_client, user):
        init = auth_client.post(reverse("wallet-topup"), {"amount": "500"})
        gw_order_id = init.data["gateway"]["order_id"]
        response = auth_client.post(
            reverse("wallet-topup-verify"),
            {
                "gateway_order_id": gw_order_id,
                "gateway_payment_id": "pay_x",
                "gateway_signature": "tampered",
            },
        )
        assert response.status_code == 400
        topup = WalletTopup.objects.get(gateway_order_id=gw_order_id)
        assert topup.status == WalletTopup.Status.FAILED
        assert get_or_create_wallet(user).balance == Decimal("0.00")

    def test_topup_minimum_amount(self, auth_client):
        response = auth_client.post(reverse("wallet-topup"), {"amount": "0"})
        assert response.status_code == 400
