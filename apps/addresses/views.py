from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Address
from .serializers import AddressSerializer


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def address_list_create(request):
    if request.method == "GET":
        addresses = Address.objects.filter(user=request.user)
        serializer = AddressSerializer(addresses, many=True)
        return Response(serializer.data)

    serializer = AddressSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def address_detail(request, address_id):
    try:
        address = Address.objects.get(id=address_id, user=request.user)
    except Address.DoesNotExist:
        return Response({"error": "Address not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(AddressSerializer(address).data)

    if request.method == "DELETE":
        address.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = AddressSerializer(address, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)
