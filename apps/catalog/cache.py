"""Versioned cache helpers for the catalog.

Cached entries are namespaced by a monotonically increasing version counter. Any
catalog write bumps the version, orphaning every old key at once (they expire by
TTL) — so invalidation is O(1) and never has to enumerate keys.
"""

from django.conf import settings
from django.core.cache import cache

VERSION_KEY = "catalog:version"


def _ttl():
    return getattr(settings, "CATALOG_CACHE_TTL", 300)


def get_version():
    version = cache.get(VERSION_KEY)
    if version is None:
        cache.set(VERSION_KEY, 1, None)  # versions never expire
        return 1
    return version


def bump_version():
    """Invalidate the whole catalog cache namespace."""
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 1, None)


def _key(suffix):
    return f"catalog:v{get_version()}:{suffix}"


def get_cached(suffix):
    return cache.get(_key(suffix))


def set_cached(suffix, data):
    cache.set(_key(suffix), data, _ttl())
