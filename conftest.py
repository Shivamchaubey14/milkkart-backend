import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """Isolate tests from each other: the locmem cache persists across the run, so
    cached catalog responses (and the version counter) must be reset per test."""
    cache.clear()
    yield
    cache.clear()
