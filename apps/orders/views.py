from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cart.models import Cart

from .models import Order, OrderItem
from .serializers import CheckoutSerializer, OrderDetailSerializer, OrderListSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def checkout(request):
    serializer = CheckoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        cart = Cart.objects.prefetch_related("items__product").get(user=request.user)
    except Cart.DoesNotExist:
        return Response({"error": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

    cart_items = list(cart.items.select_related("product").all())
    if not cart_items:
        return Response({"error": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

    # Validate stock
    for item in cart_items:
        if item.quantity > item.product.stock:
            return Response(
                {"error": f"'{item.product.name}' only has {item.product.stock} in stock."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    with transaction.atomic():
        total = sum(item.subtotal for item in cart_items)

        order = Order.objects.create(
            user=request.user,
            total=total,
            delivery_address=serializer.validated_data["delivery_address"],
            notes=serializer.validated_data.get("notes", ""),
        )

        order_items = []
        for item in cart_items:
            order_items.append(
                OrderItem(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    product_price=item.product.price,
                    quantity=item.quantity,
                )
            )
            item.product.stock -= item.quantity
            item.product.save(update_fields=["stock"])

        OrderItem.objects.bulk_create(order_items)
        cart.items.all().delete()

    return Response(
        OrderDetailSerializer(order).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    serializer = OrderListSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_detail(request, order_number):
    try:
        order = Order.objects.prefetch_related("items").get(
            order_number=order_number, user=request.user
        )
    except Order.DoesNotExist:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(OrderDetailSerializer(order).data)
