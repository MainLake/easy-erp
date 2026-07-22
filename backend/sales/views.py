"""Sales ViewSets — customer CRUD, SO lifecycle with confirm/fulfill actions."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.response import Response

from .models import Customer, SalesOrder, SOLineItem
from .serializers import (
    CustomerSerializer,
    SalesOrderSerializer,
    SOLineItemSerializer,
    SalesOrderStatusSerializer,
)
from . import services
from core import approvals
from core.permissions import OrgRolePermission


class CustomerViewSet(viewsets.ModelViewSet):
    """CRUD for customers — org-scoped."""

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Customer.objects.all().order_by('name')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('sales', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('sales', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('sales', 'write')]

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)


class SalesOrderViewSet(viewsets.ModelViewSet):
    """CRUD for sales orders + lifecycle actions (confirm, fulfill)."""

    queryset = SalesOrder.objects.all()
    serializer_class = SalesOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SalesOrder.objects.prefetch_related(
            'line_items__product', 'line_items__warehouse'
        ).order_by('-created_at')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('sales', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('sales', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('sales', 'write')]

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.organization,
            created_by=self.request.user,
        )

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """POST /api/v1/sales/orders/{id}/confirm/ — draft → confirmed (stock check).

        If an active ApprovalRule gates this order, the transition is
        blocked instead: response is 200 with approval_status='pending'
        and status unchanged (frontend branches on approval_status)."""
        try:
            so = services.confirm_so(so_id=pk, user=request.user)
        except SalesOrder.DoesNotExist:
            raise NotFound(detail='Sales order not found.')
        except DjangoValidationError as e:
            raise ValidationError(detail=e.message_dict)

        return Response(SalesOrderSerializer(so).data)

    @action(detail=True, methods=['post'])
    def fulfill(self, request, pk=None):
        """POST /api/v1/sales/orders/{id}/fulfill/ — confirmed → fulfilled (stock decrement)"""
        try:
            so = services.fulfill_so(so_id=pk)
        except SalesOrder.DoesNotExist:
            raise NotFound(detail='Sales order not found.')
        except DjangoValidationError as e:
            raise ValidationError(detail=e.message_dict)

        return Response(SalesOrderSerializer(so).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """POST /api/v1/sales/orders/{id}/approve/ — approve a pending order.

        Authority-gated via core.approvals.can_approve (403 if unauthorized).
        On success, re-invokes confirm_so so the now-approved order
        completes its original transition in the same call."""
        try:
            so = SalesOrder.objects.get(pk=pk)
        except SalesOrder.DoesNotExist:
            raise NotFound(detail='Sales order not found.')

        approvals.approve_order(order=so, order_type='sales_order', user=request.user)

        try:
            so = services.confirm_so(so_id=so.id, user=request.user)
        except DjangoValidationError as e:
            raise ValidationError(detail=e.message_dict)

        return Response(SalesOrderSerializer(so).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """POST /api/v1/sales/orders/{id}/reject/ — reject a pending order.

        Authority-gated via core.approvals.can_approve (403 if unauthorized).
        Does NOT auto-retry the blocked transition."""
        try:
            so = SalesOrder.objects.get(pk=pk)
        except SalesOrder.DoesNotExist:
            raise NotFound(detail='Sales order not found.')

        so = approvals.reject_order(order=so, order_type='sales_order', user=request.user)
        return Response(SalesOrderSerializer(so).data)
