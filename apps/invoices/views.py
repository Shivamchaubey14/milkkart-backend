import datetime

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.orders.models import Order

from .models import Invoice
from .serializers import InvoiceSerializer
from .services import build_statement, email_invoice, generate_invoice


def _parse_month(request):
    """Return (year, month) from a ?month=YYYY-MM param, defaulting to this month."""
    month_param = request.query_params.get("month")
    today = datetime.date.today()
    if not month_param:
        return today.year, today.month, None
    try:
        year, month = (int(part) for part in month_param.split("-"))
        datetime.date(year, month, 1)
    except (ValueError, TypeError):
        return None, None, "Invalid 'month' — use YYYY-MM."
    return year, month, None


class InvoiceListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        return Invoice.objects.filter(order__user=self.request.user).select_related("order")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def invoice_for_order(request, order_number):
    """Fetch (generating on first request) the invoice for one of the user's orders."""
    try:
        order = Order.objects.get(order_number=order_number, user=request.user)
    except Order.DoesNotExist:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    invoice = generate_invoice(order)
    return Response(InvoiceSerializer(invoice).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def email_invoice_view(request, order_number):
    """Generate (if needed) and e-mail the invoice for one of the user's orders."""
    try:
        order = Order.objects.get(order_number=order_number, user=request.user)
    except Order.DoesNotExist:
        return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    invoice = generate_invoice(order)
    email_invoice(invoice)
    return Response(InvoiceSerializer(invoice).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def statement(request):
    """Monthly billing statement for the authenticated user."""
    year, month, error = _parse_month(request)
    if error:
        return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

    data = build_statement(request.user, year, month)
    invoices = Invoice.objects.filter(
        order__user=request.user, issued_at__year=year, issued_at__month=month
    ).select_related("order")
    data["invoices"] = InvoiceSerializer(invoices, many=True).data
    return Response(data)
