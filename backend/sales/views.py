"""Sales ViewSets — customer CRUD, SO lifecycle with confirm/fulfill actions."""

from django.core.exceptions import ValidationError
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Customer, SalesOrder, SOLineItem
from .serializers import (
    CustomerSerializer,
    SalesOrderSerializer,
    SOLineItemSerializer,
    SalesOrderStatusSerializer,
)
from . import services
from core.permissions import IsOperator


class CustomerViewSet(viewsets.ModelViewSet):
    """CRUD for customers."""

    queryset = Customer.objects.all().order_by('name')
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsOperator]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOperator()]


class SalesOrderViewSet(viewsets.ModelViewSet):
    """CRUD for sales orders + lifecycle actions (confirm, fulfill)."""

    queryset = SalesOrder.objects.prefetch_related('line_items__product', 'line_items__warehouse').order_by('-created_at')
    serializer_class = SalesOrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOperator]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOperator()]

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """POST /api/v1/sales/orders/{id}/confirm/ — draft → confirmed (stock check)"""
        try:
            so = services.confirm_so(so_id=pk)
        except SalesOrder.DoesNotExist:
            return Response(
                {'errors': {'detail': 'Sales order not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as e:
            return Response({'errors': e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SalesOrderSerializer(so).data)

    @action(detail=True, methods=['post'])
    def fulfill(self, request, pk=None):
        """POST /api/v1/sales/orders/{id}/fulfill/ — confirmed → fulfilled (stock decrement)"""
        try:
            so = services.fulfill_so(so_id=pk)
        except SalesOrder.DoesNotExist:
            return Response(
                {'errors': {'detail': 'Sales order not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as e:
            return Response({'errors': e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SalesOrderSerializer(so).data)
