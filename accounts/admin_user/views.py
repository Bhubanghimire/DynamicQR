from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from accounts.models import User, FAQ
from accounts.serializers import UserAdminSerializer, UserAdminDetailSerializer, UserAdminCreateSerializer, UserAdminUpdateSerializer, FAQAdminSerializer
from accounts.views import AdminAutoSchema, admin_query_parameter

class UserAdminSchema(AdminAutoSchema):
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
    swagger_query_parameters = {
        "list": [
            admin_query_parameter(
                "status",
                "Filter by exact subscription status.",
                enum=["active", "expired", "cancelled", "pending", "failed", "grace_period"],
                example="active",
            ),
            admin_query_parameter(
                "plan",
                "Filter by exact package title (case-sensitive), for example `Free` or `Pro`.",
                example="Pro",
            ),
        ],
    }

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

class FAQAdminViewSet(viewsets.ModelViewSet):
    queryset = FAQ.objects.all().order_by('display_order', 'id')
    serializer_class = FAQAdminSerializer
    permission_classes = [IsAdminUser]
    schema = AdminAutoSchema()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "data": serializer.data,
                "message": "FAQs fetched successfully."
            },
            status=status.HTTP_200_OK
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(
            {
                "data": serializer.data,
                "message": "FAQ details fetched successfully."
            },
            status=status.HTTP_200_OK
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                "data": serializer.data,
                "message": "FAQ created successfully."
            },
            status=status.HTTP_201_CREATED,
            headers=headers
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
                "message": "FAQ updated successfully."
            },
            status=status.HTTP_200_OK
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {
                "data": {},
                "message": "FAQ deleted successfully."
            },
            status=status.HTTP_200_OK
        )
