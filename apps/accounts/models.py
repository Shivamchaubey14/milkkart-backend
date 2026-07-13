import random
import re
import string

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

phone_validator = RegexValidator(
    regex=r"^\+?1?\d{9,15}$",
    message="Phone number must be 9-15 digits, optionally starting with '+'.",
)


def normalize_phone(raw):
    """Canonical form for a phone number, so "9876543210", "919876543210" and
    "+919876543210" all resolve to the same account. Bare 10-digit numbers are
    assumed to be Indian (+91)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        return "+91" + digits
    return "+" + digits


class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Phone number is required")
        extra_fields.setdefault("is_active", True)
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        SUPPORT = "support", "Support agent"
        OPS = "ops", "Operations"
        WAREHOUSE = "warehouse", "Warehouse"
        ADMIN = "admin", "Administrator"

    # Roles that grant back-office access (and therefore Django-admin login).
    STAFF_ROLES = (Role.SUPPORT, Role.OPS, Role.WAREHOUSE, Role.ADMIN)

    phone = models.CharField(
        max_length=17,
        unique=True,
        validators=[phone_validator],
    )
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True, default="")
    # Profile picture as a URL or an uploaded data: URL (same approach as the
    # rider proof photo). Blank means "show initials".
    avatar = models.TextField(blank=True, default="")
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.CUSTOMER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.phone

    @property
    def is_staff_role(self):
        """True if this user holds any back-office role."""
        return self.role in self.STAFF_ROLES

    def has_role(self, *roles):
        """True for an admin/superuser, or when the user holds one of ``roles``."""
        return self.is_superuser or self.role == self.Role.ADMIN or self.role in roles


class OTP(models.Model):
    phone = models.CharField(max_length=17, validators=[phone_validator])
    code = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "otps"
        indexes = [
            models.Index(fields=["phone", "code"]),
        ]

    def __str__(self):
        return f"OTP({self.phone})"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(
                minutes=settings.OTP_EXPIRY_MINUTES,
            )
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def generate(cls, phone):
        code = "".join(random.choices(string.digits, k=settings.OTP_LENGTH))
        return cls.objects.create(phone=phone, code=code)
