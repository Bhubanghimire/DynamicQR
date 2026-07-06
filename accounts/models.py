import uuid
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.transaction import atomic
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


class User(AbstractBaseUser, PermissionsMixin, SoftDeletable):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    # last_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=255)
    # address = models.CharField(max_length=255)
    profile = models.ImageField(upload_to='profiles/', null=True, blank=True)
    birth_date = models.DateField(blank=True, null=True)
    gender = models.ForeignKey(ConfigChoice, on_delete=models.PROTECT, blank=True, null=True, related_name="gender")
    user_type = models.ForeignKey(ConfigChoice, on_delete=models.PROTECT, null=True, blank=True)
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
        return self.first_name

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"


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


