"""
Inventory domain models: Product, Category, Warehouse, StockLevel, StockMovement.

All models inherit from core.BaseModel for consistent UUID primary keys
and auto-timestamps.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel


class Category(BaseModel):
    """Product category with optional parent for hierarchy."""

    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
    )

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(BaseModel):
    """Inventory product with unique SKU, cost, and sale price."""

    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.sku})'


class Warehouse(BaseModel):
    """Physical storage location.

    Multi-org (Phase 1): a warehouse may have a manager and assistants who
    are members of the same organization.  The ``branch`` FK is added in
    Phase 3 once Branch is fully wired into the org hierarchy.
    """

    name = models.CharField(max_length=100)
    location = models.CharField(max_length=255, blank=True, default='')

    managed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses',
    )
    assistants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='assisted_warehouses',
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StockLevel(BaseModel):
    """Current stock quantity for a given product at a given warehouse.

    Enforced constraint: one row per (product, warehouse) pair.
    Quantity is always >= 0 (enforced at the service layer).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_levels')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock_levels')
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['product', 'warehouse']
        ordering = ['product', 'warehouse']

    def __str__(self):
        return f'{self.product.name} @ {self.warehouse.name}: {self.quantity}'


class StockMovement(BaseModel):
    """Audit trail for every stock change.

    Types:
        add          — stock added (receipt, return, manual)
        remove       — stock removed (fulfillment, damage, manual)
        transfer_in  — stock received from another warehouse
        transfer_out — stock sent to another warehouse
    """

    class MovementType(models.TextChoices):
        ADD = 'add', 'Add'
        REMOVE = 'remove', 'Remove'
        TRANSFER_IN = 'transfer_in', 'Transfer In'
        TRANSFER_OUT = 'transfer_out', 'Transfer Out'

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.movement_type} {self.quantity} of {self.product.name} @ {self.warehouse.name}'
