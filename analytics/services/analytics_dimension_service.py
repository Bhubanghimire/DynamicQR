from django.db.models import F

from analytics.models import AnalyticsDimension


class AnalyticsDimensionService:

    def __init__(self, context):
        self.context = context

    def update(self):
        dimension_map = {
            AnalyticsDimension.DimensionType.COUNTRY: self.context.country,
            AnalyticsDimension.DimensionType.CITY: self.context.city,
            AnalyticsDimension.DimensionType.BROWSER: self.context.browser,
            AnalyticsDimension.DimensionType.OS: self.context.os,
            AnalyticsDimension.DimensionType.DEVICE: self.context.device_type,
            AnalyticsDimension.DimensionType.LANGUAGE: self.context.language,
            AnalyticsDimension.DimensionType.REFERER: self.context.referer,
        }

        results = []
        is_unique_scan = bool(self.context.is_unique_scan)

        for dimension_type, value in dimension_map.items():
            if not value:
                continue

            parent = ""
            if dimension_type == AnalyticsDimension.DimensionType.COUNTRY:
                parent = self.context.country_code or ""
            elif dimension_type == AnalyticsDimension.DimensionType.CITY:
                parent = self.context.region or ""
            elif dimension_type == AnalyticsDimension.DimensionType.DEVICE:
                parent = self.context.device_brand or ""
            elif dimension_type == AnalyticsDimension.DimensionType.BROWSER:
                parent = self.context.browser_version or ""
            elif dimension_type == AnalyticsDimension.DimensionType.OS:
                parent = self.context.os_version or ""

            dimension, created = AnalyticsDimension.objects.get_or_create(
                qr=self.context.qr,
                dimension_type=dimension_type,
                value=value,
                defaults={
                    "parent": parent,
                    "total_scans": 1,
                    "unique_scans": 1 if is_unique_scan else 0,
                },
            )
            if not created:
                AnalyticsDimension.objects.filter(pk=dimension.pk).update(
                    parent=parent,
                    total_scans=F("total_scans") + 1,
                    unique_scans=F("unique_scans") + (1 if is_unique_scan else 0),
                )
                dimension.refresh_from_db()

            results.append(dimension)

        self.context.analytics_dimensions = results
        return results
