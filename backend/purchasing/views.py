"""Purchasing ViewSets — supplier CRUD, PO lifecycle with custom actions."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.response import Response

from .models import Supplier, PurchaseOrder, POLineItem
from .serializers import (
    SupplierSerializer,
    PurchaseOrderSerializer,
    POLineItemSerializer,
    PurchaseOrderStatusSerializer,
)
from . import services
from core.permissions import OrgRolePermission


class SupplierViewSet(viewsets.ModelViewSet):
    """CRUD for suppliers — org-scoped."""

    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Supplier.objects.all().order_by('name')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('purchasing', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('purchasing', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('purchasing', 'write')]

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """CRUD for purchase orders + lifecycle actions (send, receive)."""

    queryset = PurchaseOrder.objects.all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PurchaseOrder.objects.prefetch_related('line_items__product').order_by('-created_at')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('purchasing', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('purchasing', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('purchasing', 'write')]

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """POST /api/v1/purchasing/orders/{id}/send/ — draft → sent"""
        try:
            po = services.send_po(po_id=pk)
        except PurchaseOrder.DoesNotExist:
            raise NotFound(detail='Purchase order not found.')
        except DjangoValidationError as e:
            raise ValidationError(detail=e.message_dict)

        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """POST /api/v1/purchasing/orders/{id}/receive/ — sent → received (stock increment)"""
        try:
            po = services.receive_po(po_id=pk)
        except PurchaseOrder.DoesNotExist:
            raise NotFound(detail='Purchase order not found.')
        except DjangoValidationError as e:
            raise ValidationError(detail=e.message_dict)

        return Response(PurchaseOrderSerializer(po).data)
