from django.db import models, transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.addresses.models import Address
from apps.cart.models import Cart

from .models import DeliverySlot, Order, OrderItem
from .serializers import CheckoutSerializer, DeliverySlotSerializer, OrderDetailSerializer, OrderListSerializer
from .tasks import send_order_confirmation


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def checkout(request):
    serializer = CheckoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # Validate address
    try:
        address = Address.objects.get(id=serializer.validated_data["address_id"], user=request.user)
    except Address.DoesNotExist:
        return Response({"error": "Address not found."}, status=status.HTTP_400_BAD_REQUEST)

    # Validate delivery slot (optional)
    delivery_slot = None
    if serializer.validated_data.get("delivery_slot_id"):
        try:
            delivery_slot = DeliverySlot.objects.get(id=serializer.validated_data["delivery_slot_id"])
        except DeliverySlot.DoesNotExist:
            return Response({"error": "Delivery slot not found."}, status=status.HTTP_400_BAD_REQUEST)
        if delivery_slot.is_full:
            return Response({"error": "Delivery slot is full."}, status=status.HTTP_400_BAD_REQUEST)

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

    address_snapshot = f"{address.address_line}, {address.landmark}, {address.city}, {address.state} {address.pincode}"

    with transaction.atomic():
        total = sum(item.subtotal for item in cart_items)

        order = Order.objects.create(
            user=request.user,
            total=total,
            address=address,
            address_snapshot=address_snapshot,
            delivery_slot=delivery_slot,
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

        if delivery_slot:
            delivery_slot.booked += 1
            delivery_slot.save(update_fields=["booked"])

        cart.items.all().delete()

    send_order_confirmation.delay(order.id)

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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def delivery_slot_list(request):
    date = request.query_params.get("date")
    slots = DeliverySlot.objects.all()
    if date:
        slots = slots.filter(date=date)
    slots = slots.filter(booked__lt=models.F("capacity"))
    serializer = DeliverySlotSerializer(slots, many=True)
    return Response(serializer.data)
