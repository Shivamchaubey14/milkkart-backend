from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OTP

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = User.objects.create_user(phone="+919876543210", password="testpass123", name="Test User")
        assert user.phone == "+919876543210"
        assert user.name == "Test User"
        assert user.check_password("testpass123")
        assert user.is_active
        assert not user.is_staff
        assert not user.is_superuser

    def test_create_user_no_phone_raises(self):
        with pytest.raises(ValueError, match="Phone number is required"):
            User.objects.create_user(phone="", password="testpass123")

    def test_create_superuser(self):
        user = User.objects.create_superuser(phone="+919876543211", password="testpass123", name="Admin")
        assert user.is_staff
        assert user.is_superuser

    def test_username_field_is_phone(self):
        assert User.USERNAME_FIELD == "phone"

    def test_str(self):
        user = User(phone="+919876543210")
        assert str(user) == "+919876543210"


@pytest.mark.django_db
class TestOTPModel:
    def test_generate_creates_otp(self):
        otp = OTP.generate("+919876543210")
        assert otp.phone == "+919876543210"
        assert len(otp.code) == 6
        assert otp.code.isdigit()
        assert not otp.is_verified
        assert otp.expires_at is not None

    def test_is_expired_false_when_fresh(self):
        otp = OTP.generate("+919876543210")
        assert not otp.is_expired

    def test_is_expired_true_when_past(self):
        otp = OTP.generate("+919876543210")
        otp.expires_at = timezone.now() - timedelta(minutes=1)
        otp.save()
        assert otp.is_expired

    def test_str(self):
        otp = OTP(phone="+919876543210")
        assert str(otp) == "OTP(+919876543210)"


@pytest.mark.django_db
class TestSendOTPView:
    def setup_method(self):
        self.client = APIClient()
        self.url = reverse("otp-send")

    def test_send_otp_success(self):
        response = self.client.post(self.url, {"phone": "+919876543210"})
        assert response.status_code == 200
        assert response.data["message"] == "OTP sent successfully"
        assert OTP.objects.filter(phone="+919876543210").count() == 1

    def test_send_otp_invalid_phone(self):
        response = self.client.post(self.url, {"phone": "abc"})
        assert response.status_code == 400

    def test_send_otp_missing_phone(self):
        response = self.client.post(self.url, {})
        assert response.status_code == 400


@pytest.mark.django_db
class TestVerifyOTPView:
    def setup_method(self):
        self.client = APIClient()
        self.url = reverse("otp-verify")

    def test_verify_otp_creates_user_and_returns_tokens(self):
        otp = OTP.generate("+919876543210")
        response = self.client.post(self.url, {"phone": "+919876543210", "code": otp.code})
        assert response.status_code == 200
        assert response.data["is_new_user"] is True
        assert "access" in response.data["tokens"]
        assert "refresh" in response.data["tokens"]
        assert User.objects.filter(phone="+919876543210").exists()

    def test_verify_otp_existing_user(self):
        User.objects.create_user(phone="+919876543210", name="Existing")
        otp = OTP.generate("+919876543210")
        response = self.client.post(self.url, {"phone": "+919876543210", "code": otp.code})
        assert response.status_code == 200
        assert response.data["is_new_user"] is False

    def test_verify_otp_invalid_code(self):
        OTP.generate("+919876543210")
        response = self.client.post(self.url, {"phone": "+919876543210", "code": "000000"})
        assert response.status_code == 400
        assert response.data["error"] == "Invalid OTP"

    def test_verify_otp_expired(self):
        otp = OTP.generate("+919876543210")
        otp.expires_at = timezone.now() - timedelta(minutes=1)
        otp.save()
        response = self.client.post(self.url, {"phone": "+919876543210", "code": otp.code})
        assert response.status_code == 400
        assert response.data["error"] == "OTP has expired"

    def test_verify_otp_already_verified(self):
        otp = OTP.generate("+919876543210")
        otp.is_verified = True
        otp.save()
        response = self.client.post(self.url, {"phone": "+919876543210", "code": otp.code})
        assert response.status_code == 400

    def test_verify_otp_missing_fields(self):
        response = self.client.post(self.url, {})
        assert response.status_code == 400


@pytest.mark.django_db
class TestMeView:
    def setup_method(self):
        self.client = APIClient()
        self.url = reverse("user-me")

    def test_me_authenticated(self):
        user = User.objects.create_user(phone="+919876543210", name="Test User")
        self.client.force_authenticate(user=user)
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert response.data["phone"] == "+919876543210"
        assert response.data["name"] == "Test User"

    def test_me_unauthenticated(self):
        response = self.client.get(self.url)
        assert response.status_code == 401


@pytest.mark.django_db
class TestTokenRefresh:
    def setup_method(self):
        self.client = APIClient()

    def test_refresh_token(self):
        User.objects.create_user(phone="+919876543210", name="Test")
        otp = OTP.generate("+919876543210")
        verify_resp = self.client.post(reverse("otp-verify"), {"phone": "+919876543210", "code": otp.code})
        refresh_token = verify_resp.data["tokens"]["refresh"]

        response = self.client.post(reverse("token-refresh"), {"refresh": refresh_token})
        assert response.status_code == 200
        assert "access" in response.data

    def test_refresh_invalid_token(self):
        response = self.client.post(reverse("token-refresh"), {"refresh": "invalid-token"})
        assert response.status_code == 401


@pytest.mark.django_db
class TestOTPTask:
    def test_send_otp_sms_task(self):
        from apps.accounts.tasks import send_otp_sms

        result = send_otp_sms("919876543210", "123456")
        assert result["status"] == "sent"
        assert result["phone"] == "919876543210"
