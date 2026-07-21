"""
Invoicing domain models: Organization, Invoice, CreditDebitNote.

Invoice generation is triggered from fulfilled sales orders.
Numbering is sequential per organization (legal requirement B3).
Credit/debit notes are linked to a specific invoice.
"""

from django.db import models

from core.models import BaseModel


class Organization(BaseModel):
    """Legal entity that issues invoices.

    Single tenant for MVP — one Organization row.
    Holds the last invoice number and next note numbers
    used for sequential numbering via select_for_update().
    """

    name = models.CharField(max_length=200)
    tax_id = models.CharField(max_length=50, unique=True)
    last_invoice_number = models.PositiveIntegerField(default=0)
    next_credit_note_number = models.PositiveIntegerField(default=1)
    next_debit_note_number = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Invoice(BaseModel):
    """Invoice generated from a fulfilled sales order.

    Lifecycle: draft → issued → cancelled.
    Number is sequential and unique (e.g. INV-001).
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ISSUED = 'issued', 'Issued'
        CANCELLED = 'cancelled', 'Cancelled'

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    number = models.CharField(max_length=50, unique=True)
    sales_order = models.ForeignKey(
        'sales.SalesOrder',
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    customer = models.ForeignKey(
        'sales.Customer',
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    issued_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Invoice {self.number} — {self.customer.name}'


class CreditDebitNote(BaseModel):
    """Credit or debit note linked to an invoice.

    Each note adjusts the effective balance of the invoice.
    Notes have their own sequential numbering.
    """

    class NoteType(models.TextChoices):
        CREDIT = 'credit', 'Credit'
        DEBIT = 'debit', 'Debit'

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name='notes',
    )
    type = models.CharField(max_length=10, choices=NoteType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    number = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_type_display()} Note {self.number} — {self.amount}'
