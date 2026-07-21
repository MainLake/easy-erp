"""
Invoicing service layer — invoice generation and credit/debit notes.

Cross-app integration:
  generate_invoice() — validates SO is fulfilled, then creates invoice
    with sequential numbering using select_for_update() on the per-org
    invoicing Organization row.
  generate_credit_note() / generate_debit_note() — creates a note linked
    to an existing invoice with separate sequential numbering.

Multi-org (spec B3): invoice numbering is sequential *per organization*.
Each core Organization has its own invoicing Organization row with
independent sequencing counters.  The caller (ViewSet) must pass the
active ``core_organization_id`` when generating an invoice.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Organization, Invoice, CreditDebitNote
from sales.models import SalesOrder


def _format_invoice_number(invoice_number: int) -> str:
    """Format an invoice sequence number as INV-XXX (zero-padded)."""
    return f'INV-{invoice_number:03d}'


def _format_credit_note_number(number: int) -> str:
    """Format a credit note sequence number as CN-XXX (zero-padded)."""
    return f'CN-{number:03d}'


def _format_debit_note_number(number: int) -> str:
    """Format a debit note sequence number as DN-XXX (zero-padded)."""
    return f'DN-{number:03d}'


def _get_or_create_invoicing_org(core_organization_id) -> Organization:
    """Return the invoicing Organization row for *core_organization_id*,
    creating one with default sequencing counters if none exists.

    Uses get_or_create() with a database-level UniqueConstraint to
    prevent race conditions on concurrent invoice generation.
    """
    from core.models import Organization as CoreOrg

    core_org = CoreOrg.objects.get(id=core_organization_id)
    org, _created = Organization.objects.get_or_create(
        core_organization=core_org,
        defaults={
            'name': core_org.name,
            'tax_id': core_org.tax_id,
            'last_invoice_number': 0,
            'next_credit_note_number': 1,
            'next_debit_note_number': 1,
        },
    )
    return org


def generate_invoice(*, sales_order_id, core_organization_id=None) -> Invoice:
    """Generate an invoice from a fulfilled sales order.

    Requirements (spec B1, B3):
      - Only fulfilled SOs can be invoiced. Non-fulfilled → ValidationError.
      - Sequential numbering **per organization** via select_for_update()
        on the per-org invoicing Organization row.
      - Invoice total is computed from SO line items (quantity × unit_price).
      - ``core_organization_id`` selects which org's sequencing counters to use.
        If omitted, falls back to the SO's organization (when set).

    Returns the created Invoice.
    """
    with transaction.atomic():
        # Validate SO exists and is fulfilled (B1 spec)
        try:
            so = SalesOrder.objects.select_for_update().get(id=sales_order_id)
        except SalesOrder.DoesNotExist:
            raise ValidationError({
                'sales_order_id': f'Sales order {sales_order_id} not found.',
            })

        if so.status != SalesOrder.Status.FULFILLED:
            raise ValidationError({
                'sales_order_id': (
                    f'Invoice can only be generated from fulfilled orders. '
                    f'Current status: {so.status}.'
                ),
            })

        # Resolve the core organization for sequencing.
        if core_organization_id is None:
            if so.organization_id is None:
                raise ValidationError({
                    'core_organization_id': (
                        'Sales order has no organization assigned and no '
                        'core_organization_id was provided.'
                    ),
                })
            core_organization_id = so.organization_id

        # Lock and increment the per-org sequential invoice number (B3 spec).
        invoicing_org = _get_or_create_invoicing_org(core_organization_id)
        org = Organization.objects.select_for_update().get(id=invoicing_org.id)
        org.last_invoice_number += 1
        org.save()

        # Calculate total from SO line items
        total = sum(
            line.quantity * line.unit_price
            for line in so.line_items.all()
        )

        invoice = Invoice.objects.create(
            organization=org,
            core_organization_id=core_organization_id,
            number=_format_invoice_number(org.last_invoice_number),
            sales_order=so,
            customer=so.customer,
            total=total,
            status=Invoice.Status.ISSUED,
            issued_date=date.today(),
        )

    return invoice


def generate_credit_note(*, invoice_id: str, amount, reason: str) -> CreditDebitNote:
    """Generate a credit note linked to an existing invoice.

    Uses the issuing entity's separate credit note sequence number
    (per-org).  Amount is stored as a positive decimal.
    """
    with transaction.atomic():
        try:
            invoice = Invoice.objects.select_for_update().get(id=invoice_id)
        except Invoice.DoesNotExist:
            raise ValidationError({
                'invoice_id': f'Invoice {invoice_id} not found.',
            })

        if amount <= 0:
            raise ValidationError({
                'amount': 'Amount must be greater than zero.',
            })

        org = Organization.objects.select_for_update().get(
            id=invoice.organization_id,
        )
        note_number = org.next_credit_note_number
        org.next_credit_note_number += 1
        org.save()

        note = CreditDebitNote.objects.create(
            invoice=invoice,
            organization_id=invoice.core_organization_id,
            type=CreditDebitNote.NoteType.CREDIT,
            amount=amount,
            reason=reason,
            number=_format_credit_note_number(note_number),
        )

    return note


def generate_debit_note(*, invoice_id: str, amount, reason: str) -> CreditDebitNote:
    """Generate a debit note linked to an existing invoice.

    Uses the issuing entity's separate debit note sequence number
    (per-org).  Amount is stored as a positive decimal.
    """
    with transaction.atomic():
        try:
            invoice = Invoice.objects.select_for_update().get(id=invoice_id)
        except Invoice.DoesNotExist:
            raise ValidationError({
                'invoice_id': f'Invoice {invoice_id} not found.',
            })

        if amount <= 0:
            raise ValidationError({
                'amount': 'Amount must be greater than zero.',
            })

        org = Organization.objects.select_for_update().get(
            id=invoice.organization_id,
        )
        note_number = org.next_debit_note_number
        org.next_debit_note_number += 1
        org.save()

        note = CreditDebitNote.objects.create(
            invoice=invoice,
            organization_id=invoice.core_organization_id,
            type=CreditDebitNote.NoteType.DEBIT,
            amount=amount,
            reason=reason,
            number=_format_debit_note_number(note_number),
        )

    return note
