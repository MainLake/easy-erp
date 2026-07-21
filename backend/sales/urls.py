from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomerViewSet, SalesOrderViewSet

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'orders', SalesOrderViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
