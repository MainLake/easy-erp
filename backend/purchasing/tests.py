"""
Phase 3 tests: Purchasing (P1, P2, P3).

Spec coverage:
  P1 — Supplier CRUD with name, contact, tax_id; auto-assign org on create
  P2 — PO lifecycle: draft → sent → received. Invalid transitions → 400.
  P3 — Receiving PO MUST increment stock for each line item.
"""

import json
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from core.tests import OrgTestMixin
from core.models import Role
from inventory.models import Product, Warehouse, StockLevel
from purchasing.models import Supplier, PurchaseOrder


def _envelope(response):
    """Parse envelope-wrapped response body into {data, errors, meta}."""
    return json.loads(response.content)


class SupplierCRUDTests(OrgTestMixin, TestCase):
    """P1: Supplier CRUD with name, contact, and tax ID."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'pur-operator@easyerp.local',
            full_name='Operator User',
        )
        self.viewer_role = Role.objects.create(
            name='Purchasing Viewer',
            organization=self.org,
            permissions={'purchasing': ['read']},
        )
        self.viewer = self.create_org_user(
            'pur-viewer@easyerp.local',
            full_name='Viewer User',
            role=self.viewer_role,
        )
        self._login(self.client, self.operator)

    def test_create_supplier_succeeds(self):
        """P1: POST with valid fields → 201."""
        response = self.client.post('/api/v1/purchasing/suppliers/', {
            'name': 'Acme Corp',
            'contact': 'John Doe',
            'tax_id': 'TAX-ACME-001',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Acme Corp')
        self.assertEqual(response.data['tax_id'], 'TAX-ACME-001')

    def test_create_supplier_duplicate_tax_id_returns_400(self):
        """P1: Duplicate tax_id → 400."""
        Supplier.objects.create(
            name='First', tax_id='TAX-001', organization=self.org,
        )
        response = self.client.post('/api/v1/purchasing/suppliers/', {
            'name': 'Second',
            'contact': 'Jane',
            'tax_id': 'TAX-001',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_suppliers(self):
        """P1: GET list → 200 with suppliers."""
        Supplier.objects.create(
            name='Alpha', tax_id='T-A', organization=self.org,
        )
        Supplier.objects.create(
            name='Beta', tax_id='T-B', organization=self.org,
        )
        response = self.client.get('/api/v1/purchasing/suppliers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertEqual(body['meta']['count'], 2)

    def test_retrieve_supplier(self):
        """P1: GET detail → 200."""
        supplier = Supplier.objects.create(
            name='Test Co', tax_id='T-C', organization=self.org,
        )
        response = self.client.get(
            f'/api/v1/purchasing/suppliers/{supplier.id}/',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tax_id'], 'T-C')

    def test_viewer_cannot_create_supplier(self):
        """P1: Viewer → 403 on create."""
        viewer_client = APIClient()
        self._login(viewer_client, self.viewer)
        response = viewer_client.post('/api/v1/purchasing/suppliers/', {
            'name': 'Blocked', 'tax_id': 'T-BLOCK',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PurchaseOrderLifecycleTests(OrgTestMixin, TestCase):
    """P2: PO lifecycle — draft → sent → received. Invalid transitions → 400."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'po-operator@easyerp.local',
            full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.supplier = Supplier.objects.create(
            name='Acme Corp', tax_id='PO-TAX-001', organization=self.org,
        )
        self.product = Product.objects.create(
            sku='PO-SKU-001', name='Widget', cost='5', price='10',
            organization=self.org,
        )

    def _create_po(self, supplier, line_items=None):
        data = {'supplier': str(supplier.id)}
        if line_items:
            data['line_items_write'] = line_items
        return self.client.post(
            '/api/v1/purchasing/orders/', data, format='json',
        )

    def test_create_po_starts_as_draft(self):
        """P2: New PO defaults to draft status."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 5, 'unit_cost': '10.00'},
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'draft')

    def test_po_lifecycle_draft_to_sent(self):
        """P2: draft → sent transition succeeds."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 3, 'unit_cost': '5.00'},
        ])
        po_id = response.data['id']

        send_resp = self.client.post(
            f'/api/v1/purchasing/orders/{po_id}/send/',
        )
        self.assertEqual(send_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(send_resp.data['status'], 'sent')

    def test_po_lifecycle_sent_to_received(self):
        """P2: sent → received transition succeeds."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 2, 'unit_cost': '3.00'},
        ])
        po_id = response.data['id']

        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        receive_resp = self.client.post(
            f'/api/v1/purchasing/orders/{po_id}/receive/',
        )
        self.assertEqual(receive_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(receive_resp.data['status'], 'received')

    def test_invalid_transition_received_to_sent_returns_400(self):
        """P2: received → send again → 400 (terminal state)."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '1.00'},
        ])
        po_id = response.data['id']

        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        self.client.post(f'/api/v1/purchasing/orders/{po_id}/receive/')

        send_again = self.client.post(
            f'/api/v1/purchasing/orders/{po_id}/send/',
        )
        self.assertEqual(send_again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot transition', str(send_again.data))

    def test_invalid_transition_draft_to_received_returns_400(self):
        """P2: draft → receive (skipping sent) → 400."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '1.00'},
        ])
        po_id = response.data['id']

        receive_resp = self.client.post(
            f'/api/v1/purchasing/orders/{po_id}/receive/',
        )
        self.assertEqual(receive_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot transition', str(receive_resp.data))

    def test_sending_already_sent_po_returns_400(self):
        """P2: sent → send (double send) → 400."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '1.00'},
        ])
        po_id = response.data['id']

        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        resend = self.client.post(
            f'/api/v1/purchasing/orders/{po_id}/send/',
        )
        self.assertEqual(resend.status_code, status.HTTP_400_BAD_REQUEST)


class PurchaseOrderAuthorshipTests(OrgTestMixin, TestCase):
    """Authorship: created_by auto-populated, immutable, null-safe."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'po-author@easyerp.local',
            full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.supplier = Supplier.objects.create(
            name='Author Supplier', tax_id='AUTH-TAX-001', organization=self.org,
        )
        self.product = Product.objects.create(
            sku='AUTH-SKU-001', name='Gizmo', cost='5', price='10',
            organization=self.org,
        )

    def _create_po(self, supplier, line_items=None, extra=None):
        data = {'supplier': str(supplier.id)}
        if line_items:
            data['line_items_write'] = line_items
        if extra:
            data.update(extra)
        return self.client.post(
            '/api/v1/purchasing/orders/', data, format='json',
        )

    def test_create_purchase_order_sets_created_by(self):
        """Authorship: created PO's created_by == authenticated user."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '5.00'},
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['created_by'], self.operator.id)

    def test_create_purchase_order_ignores_spoofed_created_by(self):
        """Authorship: spoofed created_by in payload is ignored on create."""
        other_user = self.create_org_user(
            'po-other@easyerp.local', full_name='Other User',
        )
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '5.00'},
        ], extra={'created_by': str(other_user.id)})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        po = PurchaseOrder.objects.get(id=response.data['id'])
        self.assertEqual(po.created_by_id, self.operator.id)

    def test_patch_purchase_order_cannot_override_created_by(self):
        """Authorship: created_by is immutable after creation via PATCH."""
        create_resp = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '5.00'},
        ])
        po_id = create_resp.data['id']

        other_user = self.create_org_user(
            'po-patcher@easyerp.local', full_name='Patcher User',
        )
        patch_resp = self.client.patch(
            f'/api/v1/purchasing/orders/{po_id}/',
            {'created_by': str(other_user.id), 'notes': 'updated'},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)

        po = PurchaseOrder.objects.get(id=po_id)
        self.assertEqual(po.created_by_id, self.operator.id)

    def test_null_created_by_order_lists_and_serializes_without_error(self):
        """Authorship: legacy/null created_by renders created_by_name as None."""
        PurchaseOrder.objects.create(
            supplier=self.supplier, organization=self.org, created_by=None,
        )
        list_resp = self.client.get('/api/v1/purchasing/orders/')
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)

        po = PurchaseOrder.objects.filter(created_by__isnull=True).first()
        detail_resp = self.client.get(f'/api/v1/purchasing/orders/{po.id}/')
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(detail_resp.data['created_by_name'])


class PurchaseOrderReceiptTests(OrgTestMixin, TestCase):
    """P3: Receiving PO MUST increment stock for each line item."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'po-recv@easyerp.local',
            full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.supplier = Supplier.objects.create(
            name='Parts Inc', tax_id='P3-TAX', organization=self.org,
        )
        self.product_a = Product.objects.create(
            sku='P3-A', name='Part A', cost='5', price='10',
            organization=self.org,
        )
        self.product_b = Product.objects.create(
            sku='P3-B', name='Part B', cost='8', price='15',
            organization=self.org,
        )

    def test_receive_po_increments_stock(self):
        """P3: Receiving a PO creates stock levels matching line items."""
        create_resp = self.client.post('/api/v1/purchasing/orders/', {
            'supplier': str(self.supplier.id),
            'line_items_write': [
                {
                    'product': str(self.product_a.id),
                    'quantity': 10, 'unit_cost': '5.00',
                },
                {
                    'product': str(self.product_b.id),
                    'quantity': 20, 'unit_cost': '8.00',
                },
            ],
        }, format='json')
        po_id = create_resp.data['id']

        self.assertFalse(
            StockLevel.objects.filter(product=self.product_a).exists(),
        )
        self.assertFalse(
            StockLevel.objects.filter(product=self.product_b).exists(),
        )

        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        receive_resp = self.client.post(
            f'/api/v1/purchasing/orders/{po_id}/receive/',
        )
        self.assertEqual(receive_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(receive_resp.data['status'], 'received')

        # The receive-action uses the first available warehouse
        wh = Warehouse.objects.filter(organization=self.org).first()
        level_a = StockLevel.objects.get(
            product=self.product_a, warehouse=wh,
        )
        level_b = StockLevel.objects.get(
            product=self.product_b, warehouse=wh,
        )
        self.assertEqual(level_a.quantity, 10)
        self.assertEqual(level_b.quantity, 20)

    def test_receive_po_without_warehouse_auto_creates_default(self):
        """P3: Receiving with no warehouse auto-creates 'Default Warehouse'."""
        Warehouse.objects.filter(organization=self.org).delete()

        create_resp = self.client.post('/api/v1/purchasing/orders/', {
            'supplier': str(self.supplier.id),
            'line_items_write': [
                {
                    'product': str(self.product_a.id),
                    'quantity': 5, 'unit_cost': '5.00',
                },
            ],
        }, format='json')
        po_id = create_resp.data['id']

        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        receive_resp = self.client.post(
            f'/api/v1/purchasing/orders/{po_id}/receive/',
        )
        self.assertEqual(receive_resp.status_code, status.HTTP_200_OK)

        default_wh = Warehouse.objects.get(name='Default Warehouse')
        level = StockLevel.objects.get(
            product=self.product_a, warehouse=default_wh,
        )
        self.assertEqual(level.quantity, 5)


class PurchaseOrderTotalPropertyTests(OrgTestMixin, TestCase):
    """`total` property: sum(quantity * unit_cost) across line items."""

    def setUp(self):
        super().setUp()
        self.supplier = Supplier.objects.create(
            name='Total Supplier', tax_id='TOTAL-TAX-001', organization=self.org,
        )
        self.product_a = Product.objects.create(
            sku='TOTAL-PO-SKU-A', name='Part A', cost='5', price='30',
            organization=self.org,
        )
        self.product_b = Product.objects.create(
            sku='TOTAL-PO-SKU-B', name='Part B', cost='5', price='15',
            organization=self.org,
        )

    def test_total_sums_line_items(self):
        """GIVEN a PO with two line items / WHEN reading `.total` / THEN it
        equals sum(quantity * unit_cost) across all lines."""
        po = PurchaseOrder.objects.create(supplier=self.supplier, organization=self.org)
        po.line_items.create(
            product=self.product_a, quantity=4, unit_cost=Decimal('20.00'),
        )
        po.line_items.create(
            product=self.product_b, quantity=1, unit_cost=Decimal('10.00'),
        )
        self.assertEqual(po.total, Decimal('90.00'))

    def test_total_is_zero_with_no_line_items(self):
        """GIVEN a PO with no line items / WHEN reading `.total` / THEN it
        is zero (proves the sum over an empty queryset, not a stub)."""
        po = PurchaseOrder.objects.create(supplier=self.supplier, organization=self.org)
        self.assertEqual(po.total, Decimal('0'))

    def test_total_quantity_sums_line_items(self):
        """GIVEN a PO with two line items / WHEN reading `.total_quantity`
        / THEN it equals sum(quantity) across all lines."""
        po = PurchaseOrder.objects.create(supplier=self.supplier, organization=self.org)
        po.line_items.create(
            product=self.product_a, quantity=4, unit_cost=Decimal('20.00'),
        )
        po.line_items.create(
            product=self.product_b, quantity=1, unit_cost=Decimal('10.00'),
        )
        self.assertEqual(po.total_quantity, 5)

    def test_total_quantity_is_zero_with_no_line_items(self):
        """GIVEN a PO with no line items / WHEN reading `.total_quantity`
        / THEN it is zero."""
        po = PurchaseOrder.objects.create(supplier=self.supplier, organization=self.org)
        self.assertEqual(po.total_quantity, 0)


class PurchaseOrderApprovalGateTests(OrgTestMixin, TestCase):
    """Phase 2: send_po gate wiring + approve/reject actions (mirrors sales)."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'po-approval-operator@easyerp.local', full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.supplier = Supplier.objects.create(
            name='Approval Supplier', tax_id='PO-APPROVAL-TAX-001', organization=self.org,
        )
        self.product = Product.objects.create(
            sku='PO-APPROVAL-SKU-001', name='Part', cost='10', price='20',
            organization=self.org,
        )

    def _create_po(self, quantity=10, unit_cost='100.00'):
        resp = self.client.post('/api/v1/purchasing/orders/', {
            'supplier': str(self.supplier.id),
            'line_items_write': [{
                'product': str(self.product.id),
                'quantity': quantity,
                'unit_cost': unit_cost,
            }],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        return resp.data['id']

    def test_send_without_rule_unaffected(self):
        """Zero-rules-configured: send proceeds unchanged, approval_status stays 'none'."""
        po_id = self._create_po()
        resp = self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'sent')
        self.assertEqual(resp.data['approval_status'], 'none')

    def test_send_over_threshold_blocks_and_returns_pending(self):
        """Order total (1000) >= min_amount (1000) -> send blocked, 200 + pending."""
        from core.models import ApprovalRule
        ApprovalRule.objects.create(
            organization=self.org, order_type='purchase_order',
            min_amount=Decimal('1000.00'),
        )
        po_id = self._create_po(quantity=10, unit_cost='100.00')

        resp = self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'draft')
        self.assertEqual(resp.data['approval_status'], 'pending')

        po = PurchaseOrder.objects.get(id=po_id)
        self.assertEqual(po.status, 'draft')
        self.assertEqual(po.approval_status, 'pending')
        self.assertEqual(po.requested_by_id, self.operator.id)

    def test_approve_by_owner_completes_transition(self):
        """Owner approves a pending order -> approval_status='approved' and a
        subsequent send (auto re-invoked by the approve action) completes."""
        from core.models import ApprovalRule
        ApprovalRule.objects.create(
            organization=self.org, order_type='purchase_order',
            min_amount=Decimal('1000.00'),
        )
        po_id = self._create_po(quantity=10, unit_cost='100.00')
        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')

        owner_membership = self.operator.memberships.get(organization=self.org)
        owner_membership.is_owner = True
        owner_membership.save()

        resp = self.client.post(f'/api/v1/purchasing/orders/{po_id}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['approval_status'], 'approved')
        self.assertEqual(resp.data['status'], 'sent')

        po = PurchaseOrder.objects.get(id=po_id)
        self.assertEqual(po.status, 'sent')
        self.assertEqual(po.approval_status, 'approved')
        self.assertEqual(po.approved_by_id, self.operator.id)
        self.assertIsNotNone(po.approved_at)

    def test_unauthorized_approve_returns_403(self):
        """A user matching none of the authority criteria gets 403 on approve."""
        from core.models import ApprovalRule, Role
        ApprovalRule.objects.create(
            organization=self.org, order_type='purchase_order',
            min_amount=Decimal('1000.00'),
        )
        po_id = self._create_po(quantity=10, unit_cost='100.00')
        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')

        outsider_role = Role.objects.create(
            name='PO Outsider Role', organization=self.org, permissions={'purchasing': ['read']},
        )
        outsider = self.create_org_user(
            'po-approval-outsider@easyerp.local', full_name='Outsider', role=outsider_role,
        )
        outsider_client = APIClient()
        self._login(outsider_client, outsider)

        resp = outsider_client.post(f'/api/v1/purchasing/orders/{po_id}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        po = PurchaseOrder.objects.get(id=po_id)
        self.assertEqual(po.approval_status, 'pending')
