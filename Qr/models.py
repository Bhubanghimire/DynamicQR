from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
import secrets
import string
#from pytz import timezone

from accounts.views import User
from system.models import ConfigChoice, SoftDeletable


# Create your models here.
class Project(SoftDeletable):
    owner = models.ForeignKey(User, on_delete=models.RESTRICT)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.BooleanField(default=True)

    def __str__(self):
        return self.name
    

class QRCode(SoftDeletable):
    SHORT_CODE_LENGTH = 10
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200, null=True, blank=True)
    short_code = models.CharField(max_length=32, null=True, blank=True, unique=True, db_index=True, editable=False)
    link_name = models.CharField(max_length=200, null=True, blank=True, unique=True, db_index=True)
    qr_type = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='qr_type')
    status = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.RESTRICT)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.short_code:
            while True:
                candidate = "".join(
                    secrets.choice(string.ascii_letters + string.digits)
                    for _ in range(self.SHORT_CODE_LENGTH)
                )
                if candidate and not QRCode.objects.filter(short_code=candidate).exists():
                    self.short_code = candidate
                    break
        super().save(*args, **kwargs)

    def is_password_enabled(self):
        setting = QRScanSetting.objects.filter(qr_code=self).first()
        if not setting:
            return False, False
        return setting.password_enabled, setting.password


class QRCodeData(SoftDeletable):
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    content_json = models.JSONField()


class QRSchedule(SoftDeletable):
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, null=True, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    # timezone = models.CharField(max_length=100, null=True, blank=True)
    is_scheduled = models.BooleanField(default=False)


class QRScanSetting(SoftDeletable):
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    is_scan_limit = models.BooleanField(default=False)
    domain = models.URLField(null=True, blank=True)
    password_enabled = models.BooleanField(default=False)
    password = models.CharField(max_length=100, null=True, blank=True)
    scan_limit = models.PositiveIntegerField(null=True, blank=True)
    is_time_limit = models.BooleanField(default=False)
    time_limit = models.PositiveIntegerField(null=True, blank=True)  # in seconds

class TemplateDesign(SoftDeletable):
    design_data = models.JSONField()
    status = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.RESTRICT)


class QRDesign(SoftDeletable):
    qr_code = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    qr_size = models.FloatField(null=True, blank=True)
    status = models.BooleanField(default=True)
    design_data = models.JSONField()
    # eye_style = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='eye_style')
    # pattern_style = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='pattern_style')
    # foreground_color = models.CharField(max_length=7)  # Hex color code
    # background_color = models.CharField(max_length=7)  # Hex color code
    # logo = models.ImageField(upload_to='qr_logos/', null=True, blank=True)
    template = models.ForeignKey(TemplateDesign, on_delete=models.RESTRICT, null=True, blank=True)

    class Meta:
        verbose_name_plural = "QR Designs"

    def __str__(self):
        return f"Design for QR Code ID: {self.qr_code.id}"


class Invitations(SoftDeletable):
    email = models.EmailField()
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    resource_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'resource_id')
    role = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT, related_name='invitation')
    token = models.CharField(max_length=100, unique=True)
    invited_by = models.ForeignKey(User, on_delete=models.RESTRICT, related_name='invitations_sent')
    status = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invitations_accepted",
    )
    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    rejected_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invitations_rejected",
    )
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        indexes = [
            models.Index(
                fields=['content_type', 'resource_id']
            ),
            models.Index(
                fields=['email', 'status']
            ),
        ]



class SharePermissions(SoftDeletable):
    user_id = models.ForeignKey(User, on_delete=models.RESTRICT)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    resource_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'resource_id')
    role = models.ForeignKey(ConfigChoice, on_delete=models.RESTRICT)

    class Meta:
        indexes = [
            models.Index(
                fields=['content_type', 'resource_id']
            ),
            models.Index(
                fields=['user_id', 'content_type', 'resource_id']
            ),
        ]


class QrMedia(SoftDeletable):
    qrcode = models.ForeignKey(QRCode, on_delete=models.CASCADE)
    qr_code = models.OneToOneField(
        QRCode,
        on_delete=models.CASCADE,
        related_name="video_content",
    )

    title = models.CharField(max_length=255, blank=True)

    autoplay = models.BooleanField(default=False)
    loop_playlist = models.BooleanField(default=False)
    show_thumbnails = models.BooleanField(default=True)


class MediaItem(SoftDeletable):
        qr_media = models.ForeignKey(
            QrMedia,
            on_delete=models.CASCADE,
            related_name="videos",
        )
        title = models.CharField(max_length=255)
        description = models.TextField(blank=True)
        video = models.FileField(upload_to="qr/videos/")
        thumbnail = models.ImageField(
            upload_to="qr/thumbs/",
            blank=True,
            null=True,
        )
        sort_order = models.PositiveIntegerField(default=1)
        is_active = models.BooleanField(default=True)

        class Meta:
            ordering = ["sort_order"]






class QRImportJob(SoftDeletable):
    user = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="qr_import_jobs",
    )

    project = models.ForeignKey(
        "Project",
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
        related_name="qr_import_jobs",
    )

    qr_type = models.ForeignKey(
        ConfigChoice,
        on_delete=models.RESTRICT,
        related_name="qr_import_jobs",
    )

    file = models.FileField(
        upload_to="qr_imports/%Y/%m/%d/",
    )

    design_data = models.JSONField(null=True, blank=True)

    status = models.ForeignKey(
        ConfigChoice,
        on_delete=models.RESTRICT,
        related_name="qr_import_statuse",
    )

    total_rows = models.PositiveIntegerField(
        default=0,
    )

    processed_rows = models.PositiveIntegerField(
        default=0,
    )

    successful_rows = models.PositiveIntegerField(
        default=0,
    )

    failed_rows = models.PositiveIntegerField(
        default=0,
    )

    progress = models.PositiveSmallIntegerField(
        default=0,
        help_text="Import progress percentage from 0 to 100.",
    )

    error_details = models.JSONField(
        default=list,
        blank=True,
    )

    error_message = models.TextField(
        blank=True,
        null=True,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.project.name} - {self.qr_type} - {self.status}"
