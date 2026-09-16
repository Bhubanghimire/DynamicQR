from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from accounts.models import User
from accounts.serializers import UserAdminSerializer
from accounts.views import AdminAutoSchema

class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminUser]
    schema = AdminAutoSchema()

    #
    @action(detail=True, methods=['post'])
    def disable(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response(
            {"message": f"User {user.email} has been disabled."},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def enable(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response(
            {"message": f"User {user.email} has been enabled."},
            status=status.HTTP_200_OK
        )
