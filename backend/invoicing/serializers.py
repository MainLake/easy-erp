"""DRF serializers for invoicing models."""

from rest_framework import serializers

from .models import Organization, Invoice, CreditDebitNote


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'tax_id',
            'last_invoice_number', 'next_credit_note_number', 'next_debit_note_number',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'last_invoice_number',
            'next_credit_note_number', 'next_debit_note_number',
            'created_at', 'updated_at',
        ]


class CreditDebitNoteSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source='invoice.number', read_only=True)
    type_display = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = CreditDebitNote
        fields = [
            'id', 'invoice', 'invoice_number', 'type', 'type_display',
            'amount', 'reason', 'number',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'number', 'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    notes = CreditDebitNoteSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'organization', 'organization_name',
            'number', 'sales_order', 'customer', 'customer_name',
            'total', 'status', 'issued_date', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'number', 'total', 'status', 'issued_date',
            'created_at', 'updated_at',
        ]
