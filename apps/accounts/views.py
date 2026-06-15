import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.throttles import OTPRateThrottle

from .models import OTP, User
from .serializers import SendOTPSerializer, UserSerializer, UserUpdateSerializer, VerifyOTPSerializer
from .tasks import send_otp_sms

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([])
@throttle_classes([OTPRateThrottle])
def send_otp(request):
    serializer = SendOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    phone = serializer.validated_data["phone"]

    otp = OTP.generate(phone)
    send_otp_sms.delay(phone, otp.code)

    return Response(
        {"message": "OTP sent successfully"},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([])
def verify_otp(request):
    serializer = VerifyOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    phone = serializer.validated_data["phone"]
    code = serializer.validated_data["code"]

    try:
        otp = OTP.objects.filter(
            phone=phone,
            code=code,
            is_verified=False,
        ).latest("created_at")
    except OTP.DoesNotExist:
        return Response(
            {"error": "Invalid OTP"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if otp.is_expired:
        return Response(
            {"error": "OTP has expired"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp.is_verified = True
    otp.save(update_fields=["is_verified"])

    user, created = User.objects.get_or_create(phone=phone)
    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "message": "OTP verified successfully",
            "is_new_user": created,
            "tokens": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response(UserSerializer(request.user).data)
