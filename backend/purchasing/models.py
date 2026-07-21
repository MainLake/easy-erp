"""
Purchasing domain models: Supplier, PurchaseOrder, POLineItem.

Purchase Order lifecycle: draft → sent → received.
Status transitions are enforced by the service layer, not model save().
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.managers import OrgAwareManager
from core.models import BaseModel


class Supplier(BaseModel):
    """Vendor/supplier with contact and tax information."""

    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=255, blank=True, default='')
    tax_id = models.CharField(max_length=50)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        null=True,
        related_name='purchasing_suppliers',
    )

    objects = OrgAwareManager()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PurchaseOrder(BaseModel):
    """Purchase order with state machine: draft → sent → received."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SENT = 'sent', 'Sent'
        RECEIVED = 'received', 'Received'

    class ApprovalStatus(models.TextChoices):
        NONE = 'none', 'None'
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchase_orders',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    order_date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, default='')
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        null=True,
        related_name='purchasing_orders',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_purchase_orders',
    )

    # Order-approval-rules feature: threshold-gated approval workflow.
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.NONE,
        help_text='Set by core.approvals.evaluate_gate when a matching '
                   'ApprovalRule requires sign-off before confirm/send.',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_purchase_orders',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_purchase_orders',
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    objects = OrgAwareManager()

    VALID_TRANSITIONS = {
        Status.DRAFT: [Status.SENT],
        Status.SENT: [Status.RECEIVED],
        Status.RECEIVED: [],  # terminal
    }

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'PO #{self.id.hex[:8]} — {self.supplier.name}'

    @property
    def total(self):
        """Sum of quantity * unit_cost across all line items."""
        return sum(
            (li.quantity * li.unit_cost for li in self.line_items.all()),
            Decimal('0'),
        )


class POLineItem(BaseModel):
    """Individual line item on a purchase order."""

    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='line_items',
    )
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='po_line_items',
    )
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return (
            f'{self.product.name} x{self.quantity} '
            f'@ {self.unit_cost} on PO #{self.purchase_order.id.hex[:8]}'
        )
