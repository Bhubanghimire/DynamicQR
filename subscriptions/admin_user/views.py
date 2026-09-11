from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser
from django.db.models import Q
from subscriptions.models import Package, Invoice
from subscriptions.serializers import PackageSerializer, InvoiceSerializer
from accounts.views import AdminAutoSchema

class PackageViewSet(viewsets.ModelViewSet):
    queryset = Package.objects.all()
    serializer_class = PackageSerializer
    permission_classes = [IsAdminUser]
    schema = AdminAutoSchema()

class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.all().order_by("-created_at")
    serializer_class = InvoiceSerializer
    permission_classes = [IsAdminUser]
    schema = AdminAutoSchema()

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset
