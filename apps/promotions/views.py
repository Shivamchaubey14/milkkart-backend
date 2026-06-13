from decimal import Decimal

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cart.billing import cart_subtotal
from apps.cart.models import Cart

from .models import Coupon
from .serializers import CouponSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def coupon_list(request):
    """List currently-valid coupons with per-user eligibility against the live cart."""
    now = timezone.now()
    coupons = Coupon.objects.filter(is_active=True, valid_from__lte=now, valid_until__gte=now)

    cart = Cart.objects.prefetch_related("items__variant").filter(user=request.user).first()
    subtotal = cart_subtotal(cart) if cart else Decimal("0")

    serializer = CouponSerializer(
        coupons, many=True, context={"request": request, "subtotal": subtotal}
    )
    return Response(serializer.data)
