from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .jwt_serializers import CustomTokenObtainPairSerializer
from .views import UserViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login view that uses the custom serializer to embed the active org
    claim into every access-token response (spec A1)."""
    serializer_class = CustomTokenObtainPairSerializer


urlpatterns = [
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]
