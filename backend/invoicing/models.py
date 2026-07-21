"""
Invoicing domain models: Organization, Invoice, CreditDebitNote.

Invoice generation is triggered from fulfilled sales orders.
Numbering is sequential per organization (legal requirement B3).
Credit/debit notes are linked to a specific invoice.
"""

from django.db import models

from core.managers import CoreOrgAwareManager, OrgAwareManager
from core.models import BaseModel


class Organization(BaseModel):
    """Legal entity that issues invoices.

    Multi-row: each core Organization can have one invoicing Organization
    row that holds invoice sequencing counters.  Formerly a singleton for
    MVP; now supports multiple orgs.

    Holds the last invoice number and next note numbers
    used for sequential numbering via select_for_update().
    """

    name = models.CharField(max_length=200)
    tax_id = models.CharField(max_length=50)
    last_invoice_number = models.PositiveIntegerField(default=0)
    next_credit_note_number = models.PositiveIntegerField(default=1)
    next_debit_note_number = models.PositiveIntegerField(default=1)
    # Link to the core Organization for multi-org scoping.
    core_organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        null=True,
        related_name='invoicing_orgs',
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Invoice(BaseModel):
    """Invoice generated from a fulfilled sales order.

    Lifecycle: draft → issued → cancelled.
    Number is sequential per organization (e.g. INV-001).

    ``organization`` links to the invoicing Organization row that holds
    per-org sequencing counters.  ``core_organization`` points to
    ``core.Organization`` for multi-tenant scoping via OrgAwareManager.
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
    core_organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        null=True,
        related_name='invoicing_invoices',
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

    objects = CoreOrgAwareManager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Invoice {self.number} — {self.customer.name}'


class CreditDebitNote(BaseModel):
    """Credit or debit note linked to an invoice.

    Each note adjusts the effective balance of the invoice.
    Notes have their own sequential numbering per organization.

    The ``organization`` FK points to ``core.Organization`` for
    multi-tenant scoping via OrgAwareManager.
    """

    class NoteType(models.TextChoices):
        CREDIT = 'credit', 'Credit'
        DEBIT = 'debit', 'Debit'

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name='notes',
    )
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        null=True,
        related_name='invoicing_credit_debit_notes',
    )
    type = models.CharField(max_length=10, choices=NoteType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    number = models.CharField(max_length=50, unique=True)

    objects = OrgAwareManager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_type_display()} Note {self.number} — {self.amount}'
