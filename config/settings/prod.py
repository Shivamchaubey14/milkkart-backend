from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import SECRET_KEY

DEBUG = False

# A real, non-default secret is mandatory in production.
if SECRET_KEY == "insecure-dev-key-change-me":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a strong value in production.")

# --- HTTPS / transport security ---------------------------------------------
# Trust the proxy's X-Forwarded-Proto so Django knows the request was HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# --- Cookies ----------------------------------------------------------------
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

# --- Content / headers ------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Origins / database -----------------------------------------------------
CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")  # noqa: F405
    if origin
]
# Persistent DB connections reduce per-request connection overhead.
DATABASES["default"]["CONN_MAX_AGE"] = int(os.environ.get("DB_CONN_MAX_AGE", "60"))  # noqa: F405
