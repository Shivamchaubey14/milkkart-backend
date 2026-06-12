from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Product

from .models import Cart, CartItem
from .serializers import AddToCartSerializer, CartSerializer, UpdateCartItemSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cart_detail(request):
    cart, _ = Cart.objects.prefetch_related("items__product").get_or_create(user=request.user)
    serializer = CartSerializer(cart)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
    serializer = AddToCartSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    product = Product.objects.get(id=serializer.validated_data["product_id"])
    quantity = serializer.validated_data["quantity"]

    if quantity > product.stock:
        return Response(
            {"error": f"Only {product.stock} items available in stock."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cart, _ = Cart.objects.get_or_create(user=request.user)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product)

    if not created:
        item.quantity += quantity
    else:
        item.quantity = quantity

    if item.quantity > product.stock:
        return Response(
            {"error": f"Only {product.stock} items available in stock."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    item.save()

    cart.refresh_from_db()
    return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def cart_item_detail(request, item_id):
    try:
        item = CartItem.objects.select_related("product").get(
            id=item_id, cart__user=request.user
        )
    except CartItem.DoesNotExist:
        return Response({"error": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        item.delete()
        cart = Cart.objects.prefetch_related("items__product").get(user=request.user)
        return Response(CartSerializer(cart).data)

    serializer = UpdateCartItemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    quantity = serializer.validated_data["quantity"]

    if quantity > item.product.stock:
        return Response(
            {"error": f"Only {item.product.stock} items available in stock."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    item.quantity = quantity
    item.save()

    cart = Cart.objects.prefetch_related("items__product").get(user=request.user)
    return Response(CartSerializer(cart).data)
