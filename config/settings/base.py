import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load a local .env (gitignored) if present, so secrets/config can live in a file
# instead of the shell. Existing environment variables are not overridden.
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")

DEBUG = False

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "django_filters",
    "corsheaders",
    "adrf",
    "channels",
    # Local
    "apps.accounts",
    "apps.addresses",
    "apps.cart",
    "apps.catalog",
    "apps.core",
    "apps.orders",
    "apps.payments",
    "apps.promotions",
    "apps.wallet",
    "apps.delivery",
    "apps.notifications",
    "apps.subscriptions",
    "apps.invoices",
    "apps.support",
    "apps.inventory",
    "apps.reports",
    "apps.serviceability",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "milkkart"),
        "USER": os.environ.get("MYSQL_USER", "milkkart"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", "milkkart_secret"),
        "HOST": os.environ.get("MYSQL_HOST", "mysql"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "otp": "5/hour",
        # Creating a top-up hits the gateway; cap it. Status polling is cheap and
        # read-only, so it gets a generous rate for ~2 min of 3s polls per attempt.
        "topup": "60/hour",
        "topup_status": "1200/hour",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
}

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 5

# Email (SMTP). Credentials live in .env (gitignored); see EMAIL_HOST_USER /
# EMAIL_HOST_PASSWORD there. OTPs are emailed in addition to the SMS log.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "indent@shwetdharamilk.com")
# Fallback recipient for OTPs of users who have no email on file yet.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", DEFAULT_FROM_EMAIL)

# Payment gateway. "mock" keeps dev/tests hermetic; set "razorpay" in prod.
PAYMENT_GATEWAY = os.environ.get("PAYMENT_GATEWAY", "mock")
PAYMENT_GATEWAY_KEY_ID = os.environ.get("PAYMENT_GATEWAY_KEY_ID", "rzp_test_key")
PAYMENT_GATEWAY_SECRET = os.environ.get("PAYMENT_GATEWAY_SECRET", "test_gateway_secret")
# Secret for verifying inbound gateway webhooks (distinct from the checkout secret).
PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET", "test_webhook_secret")

# Merchant UPI identity for gateway-agnostic intent/QR collect requests. Set
# UPI_VPA to a real registered VPA to receive funds without a payment gateway.
UPI_VPA = os.environ.get("UPI_VPA", "milkkart@upi")
UPI_PAYEE_NAME = os.environ.get("UPI_PAYEE_NAME", "MilkKart")
# Dev/mock only: how long a top-up stays "created" before the status poll
# simulates the gateway confirming it — long enough to actually scan the QR and
# pay. Ignored entirely with a real gateway (the webhook decides). 0 = instant.
WALLET_MOCK_CONFIRM_DELAY_SECONDS = int(os.environ.get("WALLET_MOCK_CONFIRM_DELAY_SECONDS", "25"))
# Drop the merchant-style tr= reference from the UPI intent. Personal VPAs can
# get risk-declined when paid with merchant params; set true for plain P2P tests.
UPI_INTENT_OMIT_REF = os.environ.get("UPI_INTENT_OMIT_REF", "false").lower() == "true"

# Cart bill engine (all amounts in INR)
FREE_DELIVERY_THRESHOLD = Decimal(os.environ.get("FREE_DELIVERY_THRESHOLD", "199"))
DELIVERY_FEE = Decimal(os.environ.get("DELIVERY_FEE", "25"))
SMALL_CART_THRESHOLD = Decimal(os.environ.get("SMALL_CART_THRESHOLD", "99"))
SMALL_CART_FEE = Decimal(os.environ.get("SMALL_CART_FEE", "15"))
TAX_PERCENT = Decimal(os.environ.get("TAX_PERCENT", "5"))

# Inventory: warn ops/warehouse staff when a variant's stock falls to/below this.
LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", "10"))

# Flat payout a rider earns per delivered order (used in the rider day summary).
DELIVERY_RIDER_FEE = Decimal(os.environ.get("DELIVERY_RIDER_FEE", "20"))

# Serviceability: enforce the delivery-area gate at checkout / subscription create.
SERVICEABILITY_ENFORCED = os.environ.get("SERVICEABILITY_ENFORCED", "true").lower() == "true"

# Catalog response cache lifetime (seconds); invalidated on any catalog write.
CATALOG_CACHE_TTL = int(os.environ.get("CATALOG_CACHE_TTL", "300"))

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get("CHANNELS_REDIS_URL", "redis://redis:6379/3")],
        },
    }
}

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

from celery.schedules import crontab  # noqa: E402

# Milk subscriptions: customers may change a delivery until this hour the prior evening.
SUBSCRIPTION_CUTOFF_HOUR = int(os.environ.get("SUBSCRIPTION_CUTOFF_HOUR", "22"))

CELERY_BEAT_SCHEDULE = {
    # After the 10 PM cutoff, build the next morning's subscription orders.
    "generate-subscription-orders": {
        "task": "apps.subscriptions.tasks.generate_subscription_orders",
        "schedule": crontab(hour=22, minute=30),
    },
    # Evening low-balance nudge so customers can top up before the cutoff.
    "subscription-low-balance-reminders": {
        "task": "apps.subscriptions.tasks.send_low_balance_reminders",
        "schedule": crontab(hour=20, minute=0),
    },
}
