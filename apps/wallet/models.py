from decimal import Decimal

from django.conf import settings
from django.db import models, transaction


class InsufficientBalance(Exception):
    """Raised when a debit exceeds the available wallet balance."""


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "wallets"

    def __str__(self):
        return f"Wallet({self.user.phone}) — ₹{self.balance}"

    def credit(self, amount, txn_type, description="", order=None):
        """Add funds and record a ledger entry. Returns the WalletTransaction."""
        return self._apply(amount, txn_type, description, order)

    def debit(self, amount, description="", order=None):
        """Deduct funds (raises InsufficientBalance) and record a DEBIT ledger entry."""
        return self._apply(-amount, WalletTransaction.Type.DEBIT, description, order)

    def _apply(self, delta, txn_type, description, order):
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=self.pk)
            new_balance = wallet.balance + delta
            if new_balance < 0:
                raise InsufficientBalance()
            wallet.balance = new_balance
            wallet.save(update_fields=["balance", "updated_at"])
            txn = WalletTransaction.objects.create(
                wallet=wallet,
                type=txn_type,
                amount=abs(delta),
                balance_after=new_balance,
                order=order,
                description=description,
            )
            self.balance = new_balance
            return txn


class WalletTransaction(models.Model):
    class Type(models.TextChoices):
        TOPUP = "topup", "Top-up"
        DEBIT = "debit", "Debit"
        REFUND = "refund", "Refund"
        CASHBACK = "cashback", "Cashback"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=10, choices=Type.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_transactions",
    )
    description = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallet_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type} ₹{self.amount} → ₹{self.balance_after}"

    @property
    def is_credit(self):
        return self.type != self.Type.DEBIT

    @property
    def signed_amount(self):
        return self.amount if self.is_credit else -self.amount


class WalletTopup(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="topups")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    gateway_order_id = models.CharField(max_length=100, blank=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "wallet_topups"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Top-up ₹{self.amount} — {self.status}"


def get_or_create_wallet(user):
    wallet, _ = Wallet.objects.get_or_create(user=user, defaults={"balance": Decimal("0")})
    return wallet
