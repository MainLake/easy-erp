"""
Inventory service layer — the central stock authority.

All stock mutations MUST go through these functions. Other apps
(purchasing, sales, invoicing) import and call them directly.
They MUST NOT touch StockLevel or StockMovement models directly.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Product, Warehouse, StockLevel, StockMovement


def add_stock(*, product_id, warehouse_id, quantity, reason, reference=''):
    """Add stock to a warehouse.

    Returns the StockMovement record.
    Raises ValidationError if quantity <= 0 or IDs are invalid.
    """
    if quantity <= 0:
        raise ValidationError({'quantity': 'Quantity must be greater than zero.'})

    with transaction.atomic():
        product = Product.objects.select_for_update().get(id=product_id)
        warehouse = Warehouse.objects.select_for_update().get(id=warehouse_id)
        stock_level, _ = StockLevel.objects.select_for_update().get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={'quantity': 0},
        )
        stock_level.quantity += quantity
        stock_level.save()

        movement = StockMovement.objects.create(
            product=product,
            warehouse=warehouse,
            movement_type=StockMovement.MovementType.ADD,
            quantity=quantity,
            reason=reason,
            reference=reference,
        )

    return movement


def remove_stock(*, product_id, warehouse_id, quantity, reason, reference=''):
    """Remove stock from a warehouse.

    Returns the StockMovement record.
    Raises ValidationError if quantity <= 0, IDs are invalid, or stock is insufficient.
    """
    if quantity <= 0:
        raise ValidationError({'quantity': 'Quantity must be greater than zero.'})

    with transaction.atomic():
        product = Product.objects.select_for_update().get(id=product_id)
        warehouse = Warehouse.objects.select_for_update().get(id=warehouse_id)

        try:
            stock_level = StockLevel.objects.select_for_update().get(
                product=product,
                warehouse=warehouse,
            )
        except StockLevel.DoesNotExist:
            raise ValidationError({
                'quantity': f'No stock exists for {product.name} at {warehouse.name}.',
            })

        if stock_level.quantity < quantity:
            raise ValidationError({
                'quantity': (
                    f'Insufficient stock for {product.name} at {warehouse.name}. '
                    f'Requested: {quantity}, available: {stock_level.quantity}.'
                ),
            })

        stock_level.quantity -= quantity
        stock_level.save()

        movement = StockMovement.objects.create(
            product=product,
            warehouse=warehouse,
            movement_type=StockMovement.MovementType.REMOVE,
            quantity=quantity,
            reason=reason,
            reference=reference,
        )

    return movement


def transfer_stock(*, product_id, from_warehouse_id, to_warehouse_id, quantity, reason=''):
    """Transfer stock between two warehouses.

    Returns a tuple of (out_movement, in_movement), both StockMovement records.
    Raises ValidationError if quantity <= 0, IDs are invalid, or stock is insufficient.
    """
    if quantity <= 0:
        raise ValidationError({'quantity': 'Quantity must be greater than zero.'})

    if from_warehouse_id == to_warehouse_id:
        raise ValidationError({
            'to_warehouse_id': 'Source and destination warehouses must be different.',
        })

    with transaction.atomic():
        product = Product.objects.select_for_update().get(id=product_id)
        from_warehouse = Warehouse.objects.select_for_update().get(id=from_warehouse_id)
        to_warehouse = Warehouse.objects.select_for_update().get(id=to_warehouse_id)

        # --- remove from source ---
        try:
            source_level = StockLevel.objects.select_for_update().get(
                product=product,
                warehouse=from_warehouse,
            )
        except StockLevel.DoesNotExist:
            raise ValidationError({
                'quantity': f'No stock exists for {product.name} at {from_warehouse.name}.',
            })

        if source_level.quantity < quantity:
            raise ValidationError({
                'quantity': (
                    f'Insufficient stock for {product.name} at {from_warehouse.name}. '
                    f'Requested: {quantity}, available: {source_level.quantity}.'
                ),
            })

        source_level.quantity -= quantity
        source_level.save()

        out_movement = StockMovement.objects.create(
            product=product,
            warehouse=from_warehouse,
            movement_type=StockMovement.MovementType.TRANSFER_OUT,
            quantity=quantity,
            reason=reason,
        )

        # --- add to destination ---
        dest_level, _ = StockLevel.objects.select_for_update().get_or_create(
            product=product,
            warehouse=to_warehouse,
            defaults={'quantity': 0},
        )
        dest_level.quantity += quantity
        dest_level.save()

        in_movement = StockMovement.objects.create(
            product=product,
            warehouse=to_warehouse,
            movement_type=StockMovement.MovementType.TRANSFER_IN,
            quantity=quantity,
            reason=reason,
        )

    return out_movement, in_movement
