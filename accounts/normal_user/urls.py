from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import AuthViewSet, BillingAddressViewSet, ProfileViewset, GoogleLoginRedirectAPIView, GoogleLoginCompleteAPIView, GoogleOAuthExchangeAPIView, ContactUsSubmitAPIView, FAQListAPIView, WorkspaceAPIView

app_name = "accounts_user"

account_router = DefaultRouter()
account_router.register(r'auth', AuthViewSet, basename='auth')
account_router.register(r'profile', ProfileViewset, basename='profile')
account_router.register(r'billing-addresses', BillingAddressViewSet, basename='billing-addresses')

# account_router.register(r'profile', ProfileViewSet, basename='profile')
# account_router.register(r'chat', ChatViewSet, basename='chat')
# account_router.register(r'fcm_token', FCMDeviceViewSet, basename='fcm_token')
# account_router.register(r'dashboard', GlobalSearchViewSet, basename='global_search')

urlpatterns = [
    path('', include(account_router.urls)),
    path('contact-us/', ContactUsSubmitAPIView.as_view(), name='contact-us-submit'),
    path('workspace/', WorkspaceAPIView.as_view(), name='workspace'),
    path('faqs/', FAQListAPIView.as_view(), name='faq-list'),
    path('google/login/', GoogleLoginRedirectAPIView.as_view(), name='google_login'),
    path('google/login/complete/', GoogleLoginCompleteAPIView.as_view(), name='google_login_complete'),
    path('google/login/exchange/', GoogleOAuthExchangeAPIView.as_view(), name='google_login_exchange'),
    # path('api/auth/', include('dj_rest_auth.urls')),
]
