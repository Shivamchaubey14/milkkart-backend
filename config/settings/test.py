from .base import *  # noqa: F401, F403

DEBUG = False

_use_mysql = os.environ.get("MYSQL_HOST")  # noqa: F405

if _use_mysql:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("MYSQL_DATABASE", "test_milkkart"),  # noqa: F405
            "USER": os.environ.get("MYSQL_USER", "milkkart"),  # noqa: F405
            "PASSWORD": os.environ.get("MYSQL_PASSWORD", "milkkart_secret"),  # noqa: F405
            "HOST": _use_mysql,
            "PORT": os.environ.get("MYSQL_PORT", "3306"),  # noqa: F405
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
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
