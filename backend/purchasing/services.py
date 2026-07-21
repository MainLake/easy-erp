"""
Purchasing service layer — PO lifecycle and receipt workflow.

Cross-app integration: receive_po() calls inventory.services.add_stock()
for each line item when a PO transitions from "sent" to "received".
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import PurchaseOrder
from inventory import services as inventory_services


def _validate_transition(po: PurchaseOrder, new_status: str) -> None:
    """Raise ValidationError if the transition is not allowed."""
    allowed = PurchaseOrder.VALID_TRANSITIONS.get(po.status, [])
    if new_status not in [s.value for s in allowed]:
        raise ValidationError({
            'status': (
                f'Cannot transition PO from "{po.status}" to "{new_status}". '
                f'Allowed transitions: {[s.value for s in allowed]}.'
            ),
        })


def send_po(*, po_id) -> PurchaseOrder:
    """Transition a PurchaseOrder from draft → sent."""
    with transaction.atomic():
        po = PurchaseOrder.objects.select_for_update().get(id=po_id)
        _validate_transition(po, PurchaseOrder.Status.SENT)
        po.status = PurchaseOrder.Status.SENT
        po.save()
    return po


def receive_po(*, po_id) -> PurchaseOrder:
    """Transition a PurchaseOrder from sent → received.

    For each line item, calls inventory.services.add_stock() to
    increment stock at the item's warehouse (default if unspecified,
    picks the first warehouse). The PO line items reference product
    and quantity — the warehouse is resolved during receipt.

    If no warehouse is explicitly specified, we create a default
    "Receiving" warehouse and use it.
    """
    with transaction.atomic():
        po = PurchaseOrder.objects.select_for_update().get(id=po_id)
        _validate_transition(po, PurchaseOrder.Status.RECEIVED)

        # We need a warehouse for stock receipt. Look for the
        # first warehouse; if none exists, create a default one.
        from inventory.models import Warehouse
        warehouse = Warehouse.objects.select_for_update().first()
        if warehouse is None:
            warehouse = Warehouse.objects.create(
                name='Default Warehouse',
                location='Auto-created for PO receipt',
                organization_id=po.organization_id,
            )

        for line in po.line_items.select_related('product').all():
            inventory_services.add_stock(
                product_id=line.product_id,
                warehouse_id=warehouse.id,
                quantity=line.quantity,
                reason=f'PO #{po.id.hex[:8]} receipt',
                reference=f'po:{po.id}',
            )

        po.status = PurchaseOrder.Status.RECEIVED
        po.save()

    return po
