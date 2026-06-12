from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "milkkart"),  # noqa: F405
        "USER": os.environ.get("MYSQL_USER", "root"),  # noqa: F405
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", "root@123"),  # noqa: F405
        "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),  # noqa: F405
        "PORT": os.environ.get("MYSQL_PORT", "3306"),  # noqa: F405
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }
}

CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(  # noqa: F405
    "rest_framework.renderers.BrowsableAPIRenderer",
)
