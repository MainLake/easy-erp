from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .jwt_serializers import CustomTokenObtainPairSerializer
from .views import (
    ApprovalRuleViewSet,
    BranchViewSet,
    CustomFieldViewSet,
    OrganizationMembershipViewSet,
    OrganizationViewSet,
    RegisterView,
    RoleViewSet,
    SwitchOrgView,
    UserViewSet,
)

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'orgs', OrganizationViewSet)
router.register(r'branches', BranchViewSet)
router.register(r'roles', RoleViewSet)
router.register(r'memberships', OrganizationMembershipViewSet)
router.register(r'custom-fields', CustomFieldViewSet)
router.register(r'approval-rules', ApprovalRuleViewSet)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login view that uses the custom serializer to embed the active org
    claim into every access-token response (spec A1)."""
    serializer_class = CustomTokenObtainPairSerializer


urlpatterns = [
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/switch-org/', SwitchOrgView.as_view(), name='switch_org'),
    path('', include(router.urls)),
]
