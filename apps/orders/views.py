from django.db import models, transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.addresses.models import Address
from apps.cart.billing import compute_bill
from apps.cart.models import Cart
from apps.inventory.models import StockMovement
from apps.inventory.services import adjust_stock
from apps.promotions.models import Coupon, CouponRedemption
from apps.serviceability.services import is_serviceable

from .models import DeliverySlot, Order, OrderItem
from .serializers import CheckoutSerializer, DeliverySlotSerializer, OrderDetailSerializer, OrderListSerializer
from .tasks import send_order_confirmation, send_order_status_update

CANCELLABLE_STATUSES = (Order.Status.PENDING, Order.Status.CONFIRMED)


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

    address_snapshot = f"{address.address_line}, {address.landmark}, {address.city}, {address.state} {address.pincode}"

    bill = compute_bill(cart)
    # A coupon is only charged if it was still eligible at checkout time.
    coupon = cart.applied_coupon if bill["coupon_code"] else None

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

        # Record the stock reservation in the inventory ledger. Stock was already
        # verified above; lock=False reuses the fetched variant rows.
        for item in cart_items:
            adjust_stock(
                item.variant,
                -item.quantity,
                StockMovement.Reason.SALE,
                order=order,
                user=request.user,
                lock=False,
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_number):
    from apps.payments.models import Payment
    from apps.payments.tasks import process_refund
    from apps.wallet.models import WalletTransaction, get_or_create_wallet

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

    with transaction.atomic():
        # Return variants reserved at checkout to stock, via the inventory ledger.
        for item in order.items.all():
            if item.variant:
                adjust_stock(
                    item.variant,
                    item.quantity,
                    StockMovement.Reason.CANCELLATION,
                    order=order,
                    user=request.user,
                    lock=False,
                )

        # Free up the booked delivery slot.
        if order.delivery_slot and order.delivery_slot.booked > 0:
            order.delivery_slot.booked -= 1
            order.delivery_slot.save(update_fields=["booked"])

        # Settle the payment: refund if captured, otherwise void.
        payment = getattr(order, "payment", None)
        refund_payment_id = None
        if payment:
            if payment.status == Payment.Status.SUCCESS:
                payment.status = Payment.Status.REFUNDED
                payment.save(update_fields=["status", "updated_at"])
                if payment.method == Payment.Method.WALLET:
                    # Money came from the wallet — return it there immediately.
                    wallet = get_or_create_wallet(order.user)
                    wallet.credit(
                        payment.amount,
                        WalletTransaction.Type.REFUND,
                        description=f"Refund for order {order.order_number}",
                        order=order,
                    )
                else:
                    refund_payment_id = payment.id
            elif payment.status in (Payment.Status.CREATED, Payment.Status.PENDING):
                payment.status = Payment.Status.FAILED
                payment.save(update_fields=["status", "updated_at"])

        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])

    if refund_payment_id:
        process_refund.delay(refund_payment_id)
    send_order_status_update.delay(order.id, Order.Status.CANCELLED)

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
