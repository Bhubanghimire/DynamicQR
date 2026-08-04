from rest_framework import serializers
from rest_framework.viewsets import GenericViewSet


class DashboardSummarySerializer(serializers.Serializer):
    total_qrs = serializers.IntegerField()
    total_scans = serializers.IntegerField()
    unique_scans = serializers.IntegerField()
    total_visitors = serializers.IntegerField()
    top_countries = serializers.ListField(child=serializers.DictField(), default=list)
    top_cities = serializers.ListField(child=serializers.DictField(), default=list)
    top_browsers = serializers.ListField(child=serializers.DictField(), default=list)
    top_devices = serializers.ListField(child=serializers.DictField(), default=list)
    top_qrs = serializers.ListField(child=serializers.DictField(), default=list)
    scan_timeline = serializers.ListField(child=serializers.DictField(), default=list)
    recent_scans = serializers.ListField(child=serializers.DictField(), default=list)


class AnalyticsDashboardViewSet(GenericViewSet):
    serializer_class = DashboardSummarySerializer
