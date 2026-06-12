import pytest
from django.contrib.auth import get_user_model

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
