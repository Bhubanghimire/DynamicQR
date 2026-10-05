import uuid
import hashlib
import secrets
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.transaction import atomic

# from Qr.models import CustomDomain
from system.models import ConfigChoice, SoftDeletable


# Create your models here.
class UserManager(BaseUserManager):

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def get_deleted(self):
        return super().get_queryset().filter(is_deleted=True)

    def _create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')
        try:
            with atomic():
                user = self.model(email=self.normalize_email(email), **extra_fields)
                user.set_password(password)
                user.save(using=self._db)
                return user
        except Exception as e:
            raise e

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self._create_user(email, password, **extra_fields)

    def create_user(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

class Workspace(SoftDeletable):
    owner = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="owned_workspace",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    # domain = models.ForeignKey("Qr.CustomDomain", on_delete=models.PROTECT, null=True, blank=True)
    default_json = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class User(AbstractBaseUser, PermissionsMixin, SoftDeletable):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    # last_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=255, blank=True)
    # address = models.CharField(max_length=255)
    profile = models.ImageField(upload_to='profiles/', null=True, blank=True)
    birth_date = models.DateField(blank=True, null=True)
    gender = models.ForeignKey(ConfigChoice, on_delete=models.PROTECT, blank=True, null=True, related_name="gender")
    user_type = models.ForeignKey(ConfigChoice, on_delete=models.PROTECT, null=True, blank=True)
    is_two_factor_enabled = models.BooleanField(default=False)
    # workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        # ordering = ('first_name', 'last_name',)
        verbose_name = 'User'

    def __str__(self):
        return self.full_name

    def get_full_name(self):
        return f"{self.full_name}"


class OTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        # Check if the OTP is still valid (e.g., not older than 10 minutes)
        expiration_time = self.created_at + timedelta(minutes=10)
        return timezone.now() < expiration_time and not self.is_used

    class Meta:
        unique_together = (('email', 'otp'),)


class GoogleOAuthExchangeCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="google_oauth_exchange_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def generate_code(cls):
        return secrets.token_urlsafe(32)

    @classmethod
    def hash_code(cls, raw_code):
        return hashlib.sha256(raw_code.encode("utf-8")).hexdigest()

    @classmethod
    def issue_for_user(cls, user, ttl_seconds=60):
        raw_code = cls.generate_code()
        now = timezone.now()
        cls.objects.create(
            user=user,
            code_hash=cls.hash_code(raw_code),
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        return raw_code

    def is_expired(self):
        return timezone.now() >= self.expires_at


class ContactUs(models.Model):
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} <{self.email}>'


class FAQ(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        return self.question


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preference',
    )
    scan_alert = models.BooleanField(default=True)
    weekly_performance = models.BooleanField(default=True)
    product_updates = models.BooleanField(default=True)
    security_alerts = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user_id']

    def __str__(self):
        return f'Notification preferences for {self.user.email}'


class UserSession(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    session_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user_agent = models.CharField(max_length=512, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-last_seen_at', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_revoked']),
            models.Index(fields=['user', 'expires_at']),
        ]

    def __str__(self):
        return f'{self.user.email} - {self.session_id}'


class BillingAddress(SoftDeletable):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="billing_address",
    )

    full_name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)

    city = models.CharField(max_length=100)
    state_province = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)

    country = models.CharField(max_length=200)

    phone = models.CharField(max_length=30, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.country}"