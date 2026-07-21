"""
Sales domain models: Customer, SalesOrder, SOLineItem.

Sales Order lifecycle: draft → confirmed → fulfilled.
Status transitions are enforced by the service layer.
"""

from django.conf import settings
from django.db import models

from core.managers import OrgAwareManager
from core.models import BaseModel


class Customer(BaseModel):
    """Customer with contact and tax information."""

    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=255, blank=True, default='')
    tax_id = models.CharField(max_length=50)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        null=True,
        related_name='sales_customers',
    )

    objects = OrgAwareManager()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class SalesOrder(BaseModel):
    """Sales order with state machine: draft → confirmed → fulfilled."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        CONFIRMED = 'confirmed', 'Confirmed'
        FULFILLED = 'fulfilled', 'Fulfilled'

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='sales_orders',
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
        related_name='sales_orders',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_sales_orders',
    )

    objects = OrgAwareManager()

    VALID_TRANSITIONS = {
        Status.DRAFT: [Status.CONFIRMED],
        Status.CONFIRMED: [Status.FULFILLED],
        Status.FULFILLED: [],  # terminal
    }

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'SO #{self.id.hex[:8]} — {self.customer.name}'


class SOLineItem(BaseModel):
    """Individual line item on a sales order."""

    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='line_items',
    )
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='so_line_items',
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.PROTECT,
        related_name='so_line_items',
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return (
            f'{self.product.name} x{self.quantity} '
            f'@ {self.unit_price} on SO #{self.sales_order.id.hex[:8]}'
        )
