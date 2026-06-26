from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
#from pytz import timezone

from accounts.views import User
from system.models import ConfigChoice, SoftDeletable


# Create your models here.
class Project(SoftDeletable):
    owner = models.ForeignKey(User, on_delete=models.RESTRICT)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT)

    def __str__(self):
        return self.name
    

class QRCode(SoftDeletable):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    user_id = models.ForeignKey(User, on_delete=models.RESTRICT)
    name = models.CharField(max_length=200)
    qr_type = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='qr_type')
    status = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='qr_status')


class QRCodeData(SoftDeletable):
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    content_json = models.JSONField()


class QRSchedule(SoftDeletable):
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    timezone = models.CharField(max_length=100)
    is_scheduled = models.BooleanField(default=False)


class QRScanSetting(SoftDeletable):
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    is_scan_limit = models.BooleanField(default=False)
    scan_limit = models.PositiveIntegerField(null=True, blank=True)
    is_time_limit = models.BooleanField(default=False)
    time_limit = models.PositiveIntegerField(null=True, blank=True)  # in seconds


class QRDesign(SoftDeletable):
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    eye_style = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='eye_style')
    pattern_style = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='pattern_style')
    foreground_color = models.CharField(max_length=7)  # Hex color code
    background_color = models.CharField(max_length=7)  # Hex color code
    logo = models.ImageField(upload_to='qr_logos/', null=True, blank=True)
    frame = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, null=True, blank=True)

    class Meta:
        verbose_name_plural = "QR Designs"

    def __str__(self):
        return f"Design for QR Code ID: {self.qr_code.id}"




class invitations(SoftDeletable):
    email = models.EmailField()
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    resource_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'resource_id')
    role = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='role')
    token = models.CharField(max_length=100, unique=True)
    invited_by = models.ForeignKey(User, on_delete=models.RESTRICT, related_name='invitations_sent')
    status = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)



class SharePermissions(SoftDeletable):
    user_id = models.ForeignKey(User, on_delete=models.RESTRICT)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    resource_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'resource_id')
    role = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT)
