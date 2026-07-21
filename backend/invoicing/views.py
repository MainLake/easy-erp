"""Invoicing ViewSets — invoice generation, credit/debit notes, CRUD."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Organization, Invoice, CreditDebitNote
from .serializers import (
    OrganizationSerializer,
    InvoiceSerializer,
    CreditDebitNoteSerializer,
)
from . import services
from core.permissions import OrgRolePermission


class OrganizationViewSet(viewsets.ModelViewSet):
    """CRUD for legal entities (invoicing Organization)."""

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            qs = qs.filter(core_organization=org)
        return qs

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'write')]

    def perform_create(self, serializer):
        serializer.save(core_organization=self.request.organization)


class InvoiceViewSet(viewsets.ModelViewSet):
    """CRUD for invoices + generate action (from fulfilled SO)."""

    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.select_related(
            'organization', 'customer', 'sales_order',
        ).prefetch_related('notes').order_by('-created_at')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'write')]

    def perform_create(self, serializer):
        serializer.save(core_organization=self.request.organization)

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """POST /api/v1/invoicing/invoices/generate/ — create invoice from fulfilled SO.

        Request body: {"sales_order_id": "<uuid>"}

        Spec B1: Only fulfilled SOs can be invoiced. Non-fulfilled → 400.
        Spec B3: Sequential numbering via select_for_update(), per-org.
        """
        sales_order_id = request.data.get('sales_order_id')
        if not sales_order_id:
            return Response(
                {'data': None, 'errors': [{'code': 'missing_field', 'message': 'sales_order_id is required.'}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invoice = services.generate_invoice(
                sales_order_id=sales_order_id,
                core_organization_id=request.organization.id,
            )
        except ValidationError as e:
            return Response(
                {'data': None, 'errors': [{'code': 'invalid_request', 'message': str(e)}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class CreditDebitNoteViewSet(viewsets.ModelViewSet):
    """CRUD for credit/debit notes + generate actions."""

    queryset = CreditDebitNote.objects.all()
    serializer_class = CreditDebitNoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CreditDebitNote.objects.select_related('invoice').order_by('-created_at')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('invoicing', 'write')]

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

    @action(detail=False, methods=['post'])
    def generate_credit(self, request):
        """POST /api/v1/invoicing/notes/generate_credit/ — create credit note.

        Request body: {"invoice_id": "<uuid>", "amount": 100.00, "reason": "..."}

        Spec B2: Credit notes are linked to an invoice.
        """
        invoice_id = request.data.get('invoice_id')
        amount = request.data.get('amount')
        reason = request.data.get('reason', '')

        if not invoice_id or amount is None:
            return Response(
                {'data': None, 'errors': [{'code': 'missing_field', 'message': 'invoice_id and amount are required.'}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            note = services.generate_credit_note(
                invoice_id=invoice_id,
                amount=Decimal(str(amount)),
                reason=reason,
            )
        except ValidationError as e:
            return Response(
                {'data': None, 'errors': [{'code': 'invalid_request', 'message': str(e)}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(CreditDebitNoteSerializer(note).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def generate_debit(self, request):
        """POST /api/v1/invoicing/notes/generate_debit/ — create debit note.

        Request body: {"invoice_id": "<uuid>", "amount": 100.00, "reason": "..."}

        Spec B2: Debit notes are linked to an invoice.
        """
        invoice_id = request.data.get('invoice_id')
        amount = request.data.get('amount')
        reason = request.data.get('reason', '')

        if not invoice_id or amount is None:
            return Response(
                {'data': None, 'errors': [{'code': 'missing_field', 'message': 'invoice_id and amount are required.'}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            note = services.generate_debit_note(
                invoice_id=invoice_id,
                amount=Decimal(str(amount)),
                reason=reason,
            )
        except ValidationError as e:
            return Response(
                {'data': None, 'errors': [{'code': 'invalid_request', 'message': str(e)}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(CreditDebitNoteSerializer(note).data, status=status.HTTP_201_CREATED)
