from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import DeviceToken, Notification
from .serializers import DeviceTokenSerializer, NotificationPreferenceSerializer, NotificationSerializer
from .services import get_preference


class NotificationListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_count(request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return Response({"unread_count": count})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_read(request, pk):
    try:
        notification = Notification.objects.get(pk=pk, user=request.user)
    except Notification.DoesNotExist:
        return Response({"error": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at"])
    return Response(NotificationSerializer(notification).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    updated = Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    return Response({"updated": updated})


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def preferences(request):
    pref = get_preference(request.user)
    if request.method == "PUT":
        serializer = NotificationPreferenceSerializer(pref, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    return Response(NotificationPreferenceSerializer(pref).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def register_device(request):
    serializer = DeviceTokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    device, _ = DeviceToken.objects.update_or_create(
        token=serializer.validated_data["token"],
        defaults={
            "user": request.user,
            "platform": serializer.validated_data.get("platform", DeviceToken.Platform.ANDROID),
            "is_active": True,
        },
    )
    return Response(DeviceTokenSerializer(device).data, status=status.HTTP_201_CREATED)
