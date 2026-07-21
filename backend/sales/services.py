"""
Sales service layer — Sales Order lifecycle and fulfillment workflow.

Cross-app integration:
  confirm_so() — validates stock sufficiency before confirming.
  fulfill_so() — calls inventory.services.remove_stock() for each
                 line item when a SO transitions to "fulfilled".
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import SalesOrder
from inventory.models import StockLevel
from inventory import services as inventory_services


def _validate_transition(so: SalesOrder, new_status: str) -> None:
    """Raise ValidationError if the transition is not allowed."""
    allowed = SalesOrder.VALID_TRANSITIONS.get(so.status, [])
    if new_status not in [s.value for s in allowed]:
        raise ValidationError({
            'status': (
                f'Cannot transition SO from "{so.status}" to "{new_status}". '
                f'Allowed transitions: {[s.value for s in allowed]}.'
            ),
        })


def confirm_so(*, so_id) -> SalesOrder:
    """Transition a SalesOrder from draft → confirmed.

    Validates that sufficient stock exists for every line item
    BEFORE changing the status. Uses select_for_update() to
    prevent race conditions with concurrent stock mutations.

    Raises ValidationError with per-line-item details when
    stock is insufficient.
    """
    with transaction.atomic():
        so = SalesOrder.objects.select_for_update().get(id=so_id)
        _validate_transition(so, SalesOrder.Status.CONFIRMED)

        errors = {}
        for line in so.line_items.select_related('product', 'warehouse').all():
            try:
                stock_level = StockLevel.objects.select_for_update().get(
                    product=line.product,
                    warehouse=line.warehouse,
                )
                available = stock_level.quantity
            except StockLevel.DoesNotExist:
                available = 0

            if available < line.quantity:
                errors[str(line.id)] = (
                    f'Insufficient stock for "{line.product.name}" '
                    f'at {line.warehouse.name}. '
                    f'Requested: {line.quantity}, available: {available}.'
                )

        if errors:
            raise ValidationError(errors)

        so.status = SalesOrder.Status.CONFIRMED
        so.save()

    return so


def fulfill_so(*, so_id) -> SalesOrder:
    """Transition a SalesOrder from confirmed → fulfilled.

    For each line item, calls inventory.services.remove_stock()
    to decrement stock. Stock sufficiency was already validated
    at confirmation time, but the service layer still handles
    edge cases (stock removed between confirm and fulfill).

    Raises ValidationError if stock has become unavailable.
    """
    with transaction.atomic():
        so = SalesOrder.objects.select_for_update().get(id=so_id)
        _validate_transition(so, SalesOrder.Status.FULFILLED)

        for line in so.line_items.select_related('product', 'warehouse').all():
            inventory_services.remove_stock(
                product_id=line.product_id,
                warehouse_id=line.warehouse_id,
                quantity=line.quantity,
                reason=f'SO #{so.id.hex[:8]} fulfillment',
                reference=f'so:{so.id}',
            )

        so.status = SalesOrder.Status.FULFILLED
        so.save()

    return so
