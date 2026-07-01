from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.addresses.models import Address
from apps.addresses.services import coordinates_for
from apps.cart.billing import compute_bill
from apps.cart.models import Cart
from apps.core.models import StoreConfig
from apps.inventory.models import StockMovement
from apps.inventory.services import OutOfStock, adjust_stock
from apps.promotions.models import Coupon, CouponRedemption
from apps.serviceability.services import is_serviceable

from .cancellation import CANCELLABLE_STATUSES, perform_cancellation
from .models import DeliverySlot, Order, OrderItem
from .serializers import CheckoutSerializer, DeliverySlotSerializer, OrderDetailSerializer, OrderListSerializer
from .tasks import auto_assign_order, send_order_confirmation, send_order_status_update

# Statuses where the customer may still re-point the order at a different saved
# address — before anyone is out delivering it.
ADDRESS_EDITABLE_STATUSES = {Order.Status.PENDING, Order.Status.CONFIRMED}


def format_address_snapshot(address):
    """The frozen, human-readable address text stored on the order."""
    return f"{address.address_line}, {address.landmark}, {address.city}, {address.state} {address.pincode}"


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

    # Ensure coordinates so the polygon (delivery-zone) check can apply; addresses
    # are usually geocoded on save, but backfill legacy/failed ones best-effort.
    if address.latitude is None or address.longitude is None:
        coords = coordinates_for(address)
        if coords:
            address.latitude, address.longitude = coords
            address.save(update_fields=["latitude", "longitude", "updated_at"])

    if not is_serviceable(address):
        return Response(
            {"error": "We don't deliver to this address yet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate delivery slot (optional)
    delivery_slot = None
    if serializer.validated_data.get("delivery_slot_id"):
        try:
            delivery_slot = DeliverySlot.objects.get(id=serializer.validated_data["delivery_slot_id"])
        except DeliverySlot.DoesNotExist:
            return Response({"error": "Delivery slot not found."}, status=status.HTTP_400_BAD_REQUEST)
        if delivery_slot.is_full:
            return Response({"error": "Delivery slot is full."}, status=status.HTTP_400_BAD_REQUEST)

    # Delivery timing: instant (default) or a next-day pre-order. Next-day is only
    # accepted while the admin's ordering window is currently open.
    delivery_day = serializer.validated_data.get("delivery_day", "instant")
    delivery_type = Order.DeliveryType.INSTANT
    delivery_date = timezone.localdate()
    if delivery_day == "next_day":
        config = StoreConfig.get_solo()
        if not config.next_day_window_open():
            return Response(
                {
                    "error": "Next-day ordering is closed right now. Choose instant delivery, "
                    "or pre-order during the ordering window."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        delivery_type = Order.DeliveryType.NEXT_DAY
        delivery_date = timezone.localdate() + timedelta(days=1)

    try:
        cart = (
            Cart.objects.select_related("applied_coupon")
            .prefetch_related("items__variant__product")
            .get(user=request.user)
        )
    except Cart.DoesNotExist:
        return Response({"error": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

    cart_items = list(cart.items.select_related("variant__product").all())
    if not cart_items:
        return Response({"error": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

    # Validate stock
    for item in cart_items:
        if item.quantity > item.variant.stock:
            name = f"{item.variant.product.name} ({item.variant.label})"
            return Response(
                {"error": f"'{name}' only has {item.variant.stock} in stock."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    address_snapshot = format_address_snapshot(address)

    bill = compute_bill(cart)
    # A coupon is only charged if it was still eligible at checkout time.
    coupon = cart.applied_coupon if bill["coupon_code"] else None

    try:
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                subtotal=bill["subtotal"],
                discount=bill["coupon_discount"],
                delivery_fee=bill["delivery_fee"],
                small_cart_fee=bill["small_cart_fee"],
                tax=bill["tax"],
                total=bill["grand_total"],
                coupon=coupon,
                address=address,
                address_snapshot=address_snapshot,
                delivery_slot=delivery_slot,
                delivery_type=delivery_type,
                delivery_date=delivery_date,
                notes=serializer.validated_data.get("notes", ""),
            )

            order_items = [
                OrderItem(
                    order=order,
                    variant=item.variant,
                    product_name=item.variant.product.name,
                    variant_label=item.variant.label,
                    product_price=item.variant.price,
                    quantity=item.quantity,
                )
                for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)

            # Reserve stock through the ledger. lock=True re-reads each variant row
            # FOR UPDATE, so a concurrent checkout can't drive stock negative between
            # the pre-check above and this write; an oversell raises OutOfStock and
            # rolls the whole order back.
            for item in cart_items:
                adjust_stock(
                    item.variant,
                    -item.quantity,
                    StockMovement.Reason.SALE,
                    order=order,
                    user=request.user,
                    lock=True,
                )

            if delivery_slot:
                delivery_slot.booked += 1
                delivery_slot.save(update_fields=["booked"])

            if coupon:
                CouponRedemption.objects.create(
                    coupon=coupon,
                    user=request.user,
                    order=order,
                    discount_amount=bill["coupon_discount"],
                )
                Coupon.objects.filter(pk=coupon.pk).update(times_used=models.F("times_used") + 1)

            cart.applied_coupon = None
            cart.save(update_fields=["applied_coupon", "updated_at"])
            cart.items.all().delete()
    except OutOfStock:
        return Response(
            {"error": "Some items just went out of stock. Please review your cart."},
            status=status.HTTP_409_CONFLICT,
        )

    send_order_confirmation.delay(order.id)
    # Qualifying instant orders (e.g. from a known pickup point) route straight to
    # their designated rider, who gets the incoming-order alert immediately.
    auto_assign_order.delay(order.id)

    return Response(
        OrderDetailSerializer(order).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items__variant__product__images")
    serializer = OrderListSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_detail(request, order_number):
    try:
        order = Order.objects.prefetch_related("items__variant__product__images").get(
            order_number=order_number, user=request.user
        )
    except Order.DoesNotExist:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(OrderDetailSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_number):
    from apps.payments.tasks import process_refund

    try:
        order = Order.objects.select_related("delivery_slot").prefetch_related("items__variant").get(
            order_number=order_number, user=request.user
        )
    except Order.DoesNotExist:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    if order.status not in CANCELLABLE_STATUSES:
        return Response(
            {"error": f"Order cannot be cancelled once it is {order.get_status_display().lower()}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    refund_payment_id = perform_cancellation(order, request.user)
    if refund_payment_id:
        process_refund.delay(refund_payment_id)
    send_order_status_update.delay(order.id, Order.Status.CANCELLED)

    return Response(OrderDetailSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_order_address(request, order_number):
    """Re-point an in-progress order at one of the customer's other saved
    addresses (Home / Work / …). Allowed only while the order hasn't gone out
    for delivery, and only to a serviceable address."""
    try:
        order = Order.objects.select_related("address").get(
            order_number=order_number, user=request.user
        )
    except Order.DoesNotExist:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    if order.status not in ADDRESS_EDITABLE_STATUSES:
        return Response(
            {"error": f"The delivery address can't be changed once the order is {order.get_status_display().lower()}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    address_id = request.data.get("address_id")
    if not address_id:
        return Response({"error": "address_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        address = Address.objects.get(id=address_id, user=request.user)
    except Address.DoesNotExist:
        return Response({"error": "Address not found."}, status=status.HTTP_400_BAD_REQUEST)

    # Backfill coordinates so the serviceability (delivery-zone) check can apply.
    if address.latitude is None or address.longitude is None:
        coords = coordinates_for(address)
        if coords:
            address.latitude, address.longitude = coords
            address.save(update_fields=["latitude", "longitude", "updated_at"])

    if not is_serviceable(address):
        return Response(
            {"error": "We don't deliver to this address yet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    order.address = address
    order.address_snapshot = format_address_snapshot(address)
    order.save(update_fields=["address", "address_snapshot", "updated_at"])

    return Response(OrderDetailSerializer(order).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def order_window(request):
    """Public status of the next-day pre-order window so the storefront can show
    whether next-day ordering is available right now (and for which date)."""
    config = StoreConfig.get_solo()
    is_open = config.next_day_window_open()
    response = Response(
        {
            "enabled": config.next_day_enabled,
            "open": is_open,
            "start": config.next_day_window_start.strftime("%H:%M"),
            "end": config.next_day_window_end.strftime("%H:%M"),
            "next_delivery_date": (
                (timezone.localdate() + timedelta(days=1)).isoformat() if is_open else None
            ),
        }
    )
    # Never cache: an admin change to the window must be visible immediately on
    # the next storefront load (browsers/proxies otherwise reuse a stale copy).
    response["Cache-Control"] = "no-store"
    return response


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
