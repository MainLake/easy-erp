from django.contrib import admin

from .models import Organization, Invoice, CreditDebitNote


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'tax_id', 'last_invoice_number']
    search_fields = ['name', 'tax_id']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['number', 'customer', 'total', 'status', 'issued_date']
    list_filter = ['status']
    search_fields = ['number', 'customer__name']


@admin.register(CreditDebitNote)
class CreditDebitNoteAdmin(admin.ModelAdmin):
    list_display = ['number', 'type', 'invoice', 'amount', 'reason']
    list_filter = ['type']
    search_fields = ['number', 'invoice__number']
