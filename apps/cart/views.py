from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import ProductVariant
from apps.promotions.models import Coupon

from .billing import cart_subtotal
from .models import Cart, CartItem
from .serializers import AddToCartSerializer, CartSerializer, UpdateCartItemSerializer


def _load_cart(user):
    return (
        Cart.objects.select_related("applied_coupon")
        .prefetch_related("items__variant__product")
        .get(user=user)
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cart_detail(request):
    Cart.objects.get_or_create(user=request.user)
    serializer = CartSerializer(_load_cart(request.user))
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def apply_coupon(request):
    code = (request.data.get("code") or "").upper().strip()
    if not code:
        return Response({"error": "Coupon code is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        coupon = Coupon.objects.get(code=code, is_active=True)
    except Coupon.DoesNotExist:
        return Response({"error": "Invalid coupon code."}, status=status.HTTP_400_BAD_REQUEST)

    cart, _ = Cart.objects.prefetch_related("items__variant").get_or_create(user=request.user)
    eligible, reason = coupon.check_eligibility(request.user, cart_subtotal(cart))
    if not eligible:
        return Response({"error": reason}, status=status.HTTP_400_BAD_REQUEST)

    cart.applied_coupon = coupon
    cart.save(update_fields=["applied_coupon", "updated_at"])
    return Response(CartSerializer(_load_cart(request.user)).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def remove_coupon(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart.applied_coupon = None
    cart.save(update_fields=["applied_coupon", "updated_at"])
    return Response(CartSerializer(_load_cart(request.user)).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
    serializer = AddToCartSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    variant = ProductVariant.objects.get(id=serializer.validated_data["variant_id"])
    quantity = serializer.validated_data["quantity"]

    if quantity > variant.stock:
        return Response(
            {"error": f"Only {variant.stock} items available in stock."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cart, _ = Cart.objects.get_or_create(user=request.user)
    item, created = CartItem.objects.get_or_create(cart=cart, variant=variant)

    if not created:
        item.quantity += quantity
    else:
        item.quantity = quantity

    if item.quantity > variant.stock:
        return Response(
            {"error": f"Only {variant.stock} items available in stock."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    item.save()

    return Response(CartSerializer(_load_cart(request.user)).data, status=status.HTTP_200_OK)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def cart_item_detail(request, item_id):
    try:
        item = CartItem.objects.select_related("variant").get(
            id=item_id, cart__user=request.user
        )
    except CartItem.DoesNotExist:
        return Response({"error": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        item.delete()
        return Response(CartSerializer(_load_cart(request.user)).data)

    serializer = UpdateCartItemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    quantity = serializer.validated_data["quantity"]

    if quantity > item.variant.stock:
        return Response(
            {"error": f"Only {item.variant.stock} items available in stock."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    item.quantity = quantity
    item.save()

    return Response(CartSerializer(_load_cart(request.user)).data)
