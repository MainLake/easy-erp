from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SupplierViewSet, PurchaseOrderViewSet

router = DefaultRouter()
router.register(r'suppliers', SupplierViewSet)
router.register(r'orders', PurchaseOrderViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
