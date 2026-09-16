from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from accounts.models import User
from accounts.serializers import UserAdminSerializer, UserAdminDetailSerializer, UserAdminCreateSerializer, UserAdminUpdateSerializer
from accounts.views import AdminAutoSchema

class UserAdminSchema(AdminAutoSchema):
    def get_parameters(self, view, method):
        parameters = super().get_parameters(view, method) or []
        if method == 'get':
            parameters.extend([
                {
                    'name': 'status',
                    'in': 'query',
                    'description': 'Filter by subscription status (active, expired, cancelled, pending, failed, grace_period)',
                    'schema': {'type': 'string'}
                },
                {
                    'name': 'plan',
                    'in': 'query',
                    'description': 'Filter by package plan title',
                    'schema': {'type': 'string'}
                },
            ])
        return parameters

    def get_request_serializer(self, path, method):
        if method == 'post':
            from accounts.serializers import UserAdminCreateSerializer
            return UserAdminCreateSerializer()
        return super().get_request_serializer(path, method)

class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminUser]
    schema = UserAdminSchema()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return UserAdminDetailSerializer
        if self.action == 'create':
            return UserAdminCreateSerializer
        if self.action in ['update', 'partial_update']:
            return UserAdminUpdateSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        from subscriptions.models import Subscription
        Subscription.get_or_create_default_subscription(user)

        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                "data": serializer.data,
                "message": "User created successfully by admin."
            },
            status=status.HTTP_201_CREATED,
            headers=headers
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(
            {
                "data": serializer.data,
                "message": "User details fetched successfully."
            },
            status=status.HTTP_200_OK
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(
            {
                "data": serializer.data,
                "message": "User profile updated successfully."
            },
            status=status.HTTP_200_OK
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def get_queryset(self):
        queryset = User.objects.all().order_by('-date_joined')
        status = self.request.query_params.get('status')
        plan = self.request.query_params.get('plan')

        if status:
            queryset = queryset.filter(subscriptions__status=status)
        if plan:
            queryset = queryset.filter(subscriptions__package_plan__package__title=plan)

        return queryset.distinct()

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
