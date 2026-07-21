"""Purchasing ViewSets — supplier CRUD, PO lifecycle with custom actions."""

from django.core.exceptions import ValidationError
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Supplier, PurchaseOrder, POLineItem
from .serializers import (
    SupplierSerializer,
    PurchaseOrderSerializer,
    POLineItemSerializer,
    PurchaseOrderStatusSerializer,
)
from . import services
from core.permissions import IsOperator


class SupplierViewSet(viewsets.ModelViewSet):
    """CRUD for suppliers."""

    queryset = Supplier.objects.all().order_by('name')
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated, IsOperator]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOperator()]


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """CRUD for purchase orders + lifecycle actions (send, receive)."""

    queryset = PurchaseOrder.objects.prefetch_related('line_items__product').order_by('-created_at')
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOperator]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOperator()]

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """POST /api/v1/purchasing/orders/{id}/send/ — draft → sent"""
        try:
            po = services.send_po(po_id=pk)
        except PurchaseOrder.DoesNotExist:
            return Response(
                {'errors': {'detail': 'Purchase order not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as e:
            return Response({'errors': e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """POST /api/v1/purchasing/orders/{id}/receive/ — sent → received (stock increment)"""
        try:
            po = services.receive_po(po_id=pk)
        except PurchaseOrder.DoesNotExist:
            return Response(
                {'errors': {'detail': 'Purchase order not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as e:
            return Response({'errors': e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PurchaseOrderSerializer(po).data)
