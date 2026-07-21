from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrganizationViewSet, InvoiceViewSet, CreditDebitNoteViewSet

router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet)
router.register(r'invoices', InvoiceViewSet)
router.register(r'notes', CreditDebitNoteViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
