from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "carts"

    def __str__(self):
        return f"Cart({self.user.phone})"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.select_related("product").all())

    @property
    def item_count(self):
        return self.items.count()


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cart_items"
        unique_together = ("cart", "product")

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    @property
    def subtotal(self):
        return self.product.price * self.quantity
