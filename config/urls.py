from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.catalog.urls")),
    path("api/v1/cart/", include("apps.cart.urls")),
    path("api/v1/orders/", include("apps.orders.urls")),
    path("api/v1/addresses/", include("apps.addresses.urls")),
    path("api/v1/payments/", include("apps.payments.urls")),
    path("api/v1/coupons/", include("apps.promotions.urls")),
    path("api/v1/wallet/", include("apps.wallet.urls")),
    path("api/v1/rider/", include("apps.delivery.urls")),
]
