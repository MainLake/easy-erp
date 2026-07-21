"""
Invoicing service layer — invoice generation and credit/debit notes.

Cross-app integration:
  generate_invoice() — validates SO is fulfilled, then creates invoice
    with sequential numbering using select_for_update() on Organization.
  generate_credit_note() / generate_debit_note() — creates a note linked
    to an existing invoice with separate sequential numbering.
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


def _get_or_create_organization() -> Organization:
    """Return the single Organization for MVP (creates a default if missing)."""
    org = Organization.objects.first()
    if org is None:
        org = Organization.objects.create(
            name='Default Organization',
            tax_id='DEFAULT-TAX-ID',
        )
    return org


def generate_invoice(*, sales_order_id) -> Invoice:
    """Generate an invoice from a fulfilled sales order.

    Requirements (spec B1, B3):
      - Only fulfilled SOs can be invoiced. Non-fulfilled → ValidationError.
      - Sequential numbering via select_for_update() on Organization.
      - Invoice total is computed from SO line items (quantity × unit_price).

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

        # Lock and increment the sequential invoice number (B3 spec)
        org = (_get_or_create_organization()
               if not Organization.objects.select_for_update().exists()
               else Organization.objects.select_for_update().first())
        org = Organization.objects.select_for_update().get(id=org.id)
        org.last_invoice_number += 1
        org.save()

        # Calculate total from SO line items
        total = sum(
            line.quantity * line.unit_price
            for line in so.line_items.all()
        )

        invoice = Invoice.objects.create(
            organization=org,
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

    Uses the Organization's separate credit note sequence number.
    Amount is stored as a positive decimal (the note expresses credit).
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

        org = Organization.objects.select_for_update().get(id=invoice.organization_id)
        note_number = org.next_credit_note_number
        org.next_credit_note_number += 1
        org.save()

        note = CreditDebitNote.objects.create(
            invoice=invoice,
            type=CreditDebitNote.NoteType.CREDIT,
            amount=amount,
            reason=reason,
            number=_format_credit_note_number(note_number),
        )

    return note


def generate_debit_note(*, invoice_id: str, amount, reason: str) -> CreditDebitNote:
    """Generate a debit note linked to an existing invoice.

    Uses the Organization's separate debit note sequence number.
    Amount is stored as a positive decimal (the note expresses debit).
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

        org = Organization.objects.select_for_update().get(id=invoice.organization_id)
        note_number = org.next_debit_note_number
        org.next_debit_note_number += 1
        org.save()

        note = CreditDebitNote.objects.create(
            invoice=invoice,
            type=CreditDebitNote.NoteType.DEBIT,
            amount=amount,
            reason=reason,
            number=_format_debit_note_number(note_number),
        )

    return note
