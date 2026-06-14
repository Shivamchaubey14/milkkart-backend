"""Invalidate the catalog cache whenever catalog data changes."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import bump_version
from .models import Category, Product, ProductImage, ProductVariant


@receiver(post_save, sender=Category)
@receiver(post_save, sender=Product)
@receiver(post_save, sender=ProductVariant)
@receiver(post_save, sender=ProductImage)
@receiver(post_delete, sender=Category)
@receiver(post_delete, sender=Product)
@receiver(post_delete, sender=ProductVariant)
@receiver(post_delete, sender=ProductImage)
def invalidate_catalog_cache(sender, **kwargs):
    bump_version()
