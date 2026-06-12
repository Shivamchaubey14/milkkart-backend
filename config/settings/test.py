from .base import *  # noqa: F401, F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "test_milkkart"),  # noqa: F405
        "USER": os.environ.get("MYSQL_USER", "milkkart"),  # noqa: F405
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", "milkkart_secret"),  # noqa: F405
        "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),  # noqa: F405
        "PORT": os.environ.get("MYSQL_PORT", "3306"),  # noqa: F405
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
