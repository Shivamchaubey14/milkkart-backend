from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# When reached through an HTTPS tunnel (e.g. ngrok → http runserver), trust the
# proxy's scheme header so absolute URLs (media/image links) come back as https.
# Android release builds block cleartext http, so this keeps images loadable.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Serve ASGI (Channels/WebSockets) from `runserver` in dev. daphne must come first.
INSTALLED_APPS = ["daphne", *INSTALLED_APPS]  # noqa: F405

# Use the in-process channel layer in dev: the bundled Redis may predate the
# BZPOPMIN command that channels-redis needs. Broadcasts triggered within the
# runserver process (e.g. rider location, order status) reach connected clients.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Run Celery tasks inline in dev (no broker/worker needed) so order-status
# broadcasts and notifications happen during the request, in the runserver process.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Use an in-process cache in dev so the cache-backed views (catalog products /
# categories) work without a running Redis. base.py points CACHES at redis:6379,
# the Docker hostname, which doesn't resolve when running runserver locally.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "milkkart-dev",
    }
}

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

# No request throttling in local dev (anon/user/OTP limits get in the way while
# developing, and the counts persist in Redis). Production keeps the base limits.
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"anon": None, "user": None, "otp": None}  # noqa: F405
