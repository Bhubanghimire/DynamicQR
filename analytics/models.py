from django.db import models
from Qr.models import QRCode
from django.utils import timezone



class Visitor(models.Model):

    """
    Unique visitor information.
    """
    visitor_hash = models.CharField(max_length=64,unique=True,db_index=True)
    """Cookie UUID+User Agent+Accept Language"""
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    total_scans = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "analytics_visitors"

    def __str__(self):
        return self.visitor_hash



class QRAnalytics(models.Model):
    """
    Cached analytics summary for a QR.
    One row per QR.
    """
    qr = models.OneToOneField(
        QRCode,
        on_delete=models.CASCADE,
        related_name="analytics",
    )
    total_scans = models.PositiveBigIntegerField(default=0)
    unique_scans = models.PositiveBigIntegerField(default=0)
    first_scan_at = models.DateTimeField(null=True,blank=True)
    last_scan_at = models.DateTimeField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "analytics_qr_summary"

    def __str__(self):
        return str(self.qr)


class ScanEvent(models.Model):
    """
    Every QR scan is stored here.
    This is the source of truth.
    """
    qr = models.ForeignKey(
        QRCode,
        on_delete=models.CASCADE,
        related_name="scan_events",
    )
    visitor = models.ForeignKey(
        Visitor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_events",
    )
    scanned_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    referer = models.TextField(
        blank=True,
        default="",
    )
    language = models.CharField(
        max_length=20,
        blank=True,
    )
    country_code = models.CharField(
        max_length=5,
        blank=True,
    )
    country = models.CharField(
        max_length=100,
        blank=True,
    )
    region = models.CharField(
        max_length=100,
        blank=True,
    )
    city = models.CharField(
        max_length=100,
        blank=True,
    )
    timezone = models.CharField(
        max_length=100,
        blank=True,
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    browser = models.CharField(
        max_length=50,
        blank=True,
    )
    browser_version = models.CharField(
        max_length=30,
        blank=True,
    )
    os = models.CharField(
        max_length=50,
        blank=True,
    )
    os_version = models.CharField(
        max_length=30,
        blank=True,
    )
    device_type = models.CharField(
        max_length=30,
        blank=True,
    )

    device_brand = models.CharField(
        max_length=50,
        blank=True,
    )

    device_model = models.CharField(
        max_length=100,
        blank=True,
    )

    screen_width = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    screen_height = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    is_bot = models.BooleanField(default=False)

    class Meta:
        db_table = "analytics_scan_events"

        indexes = [
            models.Index(fields=["qr", "scanned_at"]),
            models.Index(fields=["visitor"]),
            models.Index(fields=["country_code"]),
            models.Index(fields=["city"]),
            models.Index(fields=["browser"]),
            models.Index(fields=["os"]),
            models.Index(fields=["device_type"]),
        ]

    def __str__(self):
        return f"{self.qr_id} - {self.scanned_at}"



class AnalyticsTime(models.Model):
    """
    Daily and hourly analytics.

    hour = NULL  -> Daily statistics
    hour = 0-23  -> Hourly statistics
    """

    qr = models.ForeignKey(
        QRCode,
        on_delete=models.CASCADE,
        related_name="time_analytics",
    )

    date = models.DateField()

    hour = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    total_scans = models.PositiveIntegerField(default=0)

    unique_scans = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "analytics_time"

        constraints = [
            models.UniqueConstraint(
                fields=["qr", "date", "hour"],
                name="unique_qr_date_hour",
            )
        ]

        indexes = [
            models.Index(fields=["qr", "date"]),
        ]

    def __str__(self):
        return f"{self.qr_id} {self.date} {self.hour}"



class AnalyticsDimension(models.Model):
    """
    Generic analytics dimensions.

    Examples:

    COUNTRY
    CITY
    BROWSER
    OS
    DEVICE
    LANGUAGE
    REFERER
    """

    class DimensionType(models.TextChoices):

        COUNTRY = "COUNTRY", "Country"

        CITY = "CITY", "City"

        BROWSER = "BROWSER", "Browser"

        OS = "OS", "Operating System"

        DEVICE = "DEVICE", "Device"

        LANGUAGE = "LANGUAGE", "Language"

        REFERER = "REFERER", "Referer"

    qr = models.ForeignKey(
        QRCode,
        on_delete=models.CASCADE,
        related_name="dimension_analytics",
    )

    dimension_type = models.CharField(
        max_length=20,
        choices=DimensionType.choices,
    )

    value = models.CharField(
        max_length=150,
    )

    parent = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Used for grouping (e.g. Kathmandu -> NP)",
    )

    total_scans = models.PositiveIntegerField(default=0)

    unique_scans = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "analytics_dimensions"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "qr",
                    "dimension_type",
                    "value",
                ],
                name="unique_dimension",
            )
        ]

        indexes = [
            models.Index(fields=["qr", "dimension_type"]),
            models.Index(fields=["value"]),
        ]

    def __str__(self):
        return f"{self.dimension_type}: {self.value}"

