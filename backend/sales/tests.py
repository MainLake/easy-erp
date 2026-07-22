"""
Phase 3 tests: Sales (S1, S2, S3).

Spec coverage:
  S1 — Customer CRUD with name, contact, tax_id; auto-assign org on create
  S2 — Sales order lifecycle: draft → confirmed → fulfilled.
        Confirming with insufficient stock → 400.
  S3 — Fulfilling a sales order MUST decrement stock.
"""

import json
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from core.tests import OrgTestMixin
from core.models import Role
from inventory.models import Product, Warehouse, StockLevel
from sales.models import Customer, SalesOrder, SOLineItem
from inventory import services as inventory_services


def _envelope(response):
    """Parse envelope-wrapped response body into {data, errors, meta}."""
    return json.loads(response.content)


class CustomerCRUDTests(OrgTestMixin, TestCase):
    """S1: Customer CRUD with name, contact, and tax ID."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'sales-operator@easyerp.local',
            full_name='Operator User',
        )
        self.viewer_role = Role.objects.create(
            name='Sales Viewer',
            organization=self.org,
            permissions={'sales': ['read']},
        )
        self.viewer = self.create_org_user(
            'sales-viewer@easyerp.local',
            full_name='Viewer User',
            role=self.viewer_role,
        )
        self._login(self.client, self.operator)

    def test_create_customer_succeeds(self):
        """S1: POST with valid fields → 201."""
        response = self.client.post('/api/v1/sales/customers/', {
            'name': 'Best Client Ltd',
            'contact': 'Alice Smith',
            'tax_id': 'CUST-TAX-001',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Best Client Ltd')

    def test_create_customer_duplicate_tax_id_returns_400(self):
        """S1: Duplicate tax_id → 400."""
        Customer.objects.create(
            name='First', tax_id='C-TAX-001', organization=self.org,
        )
        response = self.client.post('/api/v1/sales/customers/', {
            'name': 'Second',
            'contact': 'Bob',
            'tax_id': 'C-TAX-001',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_customers(self):
        """S1: GET list → 200."""
        Customer.objects.create(
            name='A Client', tax_id='T-A', organization=self.org,
        )
        Customer.objects.create(
            name='B Client', tax_id='T-B', organization=self.org,
        )
        response = self.client.get('/api/v1/sales/customers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertEqual(body['meta']['count'], 2)

    def test_retrieve_customer(self):
        """S1: GET detail → 200."""
        customer = Customer.objects.create(
            name='Target', tax_id='T-T', organization=self.org,
        )
        response = self.client.get(
            f'/api/v1/sales/customers/{customer.id}/',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Target')

    def test_viewer_cannot_create_customer(self):
        """S1: Viewer → 403 on create."""
        viewer_client = APIClient()
        self._login(viewer_client, self.viewer)
        response = viewer_client.post('/api/v1/sales/customers/', {
            'name': 'Blocked', 'tax_id': 'T-BLOCK',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SalesOrderLifecycleTests(OrgTestMixin, TestCase):
    """S2: SO lifecycle; confirming with insufficient stock → 400."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'so-operator@easyerp.local',
            full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.customer = Customer.objects.create(
            name='Test Customer', tax_id='SO-TAX-001', organization=self.org,
        )
        self.product = Product.objects.create(
            sku='SO-SKU-001', name='Gadget', cost='10', price='25',
            organization=self.org,
        )

    def _create_so(self, customer, line_items=None):
        data = {'customer': str(customer.id)}
        if line_items:
            data['line_items_write'] = line_items
        return self.client.post('/api/v1/sales/orders/', data, format='json')

    def test_create_so_starts_as_draft(self):
        """S2: New SO defaults to draft status."""
        response = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 3,
                'unit_price': '25.00',
            },
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'draft')

    def test_so_lifecycle_draft_to_confirmed(self):
        """S2: draft → confirmed when stock is sufficient."""
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=10,
            reason='test stock',
        )

        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 5,
                'unit_price': '25.00',
            },
        ])
        so_id = create_resp.data['id']

        confirm_resp = self.client.post(
            f'/api/v1/sales/orders/{so_id}/confirm/',
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_resp.data['status'], 'confirmed')

    def test_so_lifecycle_confirmed_to_fulfilled(self):
        """S2: confirmed → fulfilled succeeds."""
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=10,
            reason='test stock',
        )

        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 5,
                'unit_price': '25.00',
            },
        ])
        so_id = create_resp.data['id']

        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        fulfill_resp = self.client.post(
            f'/api/v1/sales/orders/{so_id}/fulfill/',
        )
        self.assertEqual(fulfill_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(fulfill_resp.data['status'], 'fulfilled')

    def test_confirm_with_insufficient_stock_returns_400(self):
        """S2: Confirming with not enough stock → 400."""
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=3,
            reason='limited stock',
        )

        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 5,
                'unit_price': '25.00',
            },
        ])
        so_id = create_resp.data['id']

        confirm_resp = self.client.post(
            f'/api/v1/sales/orders/{so_id}/confirm/',
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Insufficient stock', str(confirm_resp.data))

        so = SalesOrder.objects.get(id=so_id)
        self.assertEqual(so.status, 'draft')

    def test_confirm_with_no_stock_at_all_returns_400(self):
        """S2: Confirming with zero stock → 400."""
        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 1,
                'unit_price': '25.00',
            },
        ])
        so_id = create_resp.data['id']

        confirm_resp = self.client.post(
            f'/api/v1/sales/orders/{so_id}/confirm/',
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_transition_fulfilled_to_confirmed_returns_400(self):
        """S2: Cannot transition from fulfilled → confirmed (terminal)."""
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=10,
            reason='test stock',
        )

        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 2,
                'unit_price': '25.00',
            },
        ])
        so_id = create_resp.data['id']

        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')

        reconfirm = self.client.post(
            f'/api/v1/sales/orders/{so_id}/confirm/',
        )
        self.assertEqual(reconfirm.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_sales_order_sets_created_by_to_authenticated_user(self):
        """Authorship: created SO's created_by == authenticated user."""
        response = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 1,
                'unit_price': '25.00',
            },
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['created_by'], self.operator.id)

    def test_create_sales_order_ignores_spoofed_created_by(self):
        """Authorship: spoofed created_by in payload is ignored on create."""
        other_user = self.create_org_user(
            'so-other@easyerp.local', full_name='Other User',
        )
        data = {
            'customer': str(self.customer.id),
            'created_by': str(other_user.id),
            'line_items_write': [
                {
                    'product': str(self.product.id),
                    'warehouse': str(self.warehouse.id),
                    'quantity': 1,
                    'unit_price': '25.00',
                },
            ],
        }
        response = self.client.post('/api/v1/sales/orders/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        so = SalesOrder.objects.get(id=response.data['id'])
        self.assertEqual(so.created_by_id, self.operator.id)

    def test_patch_sales_order_cannot_override_created_by(self):
        """Authorship: created_by is immutable after creation via PATCH."""
        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 1,
                'unit_price': '25.00',
            },
        ])
        so_id = create_resp.data['id']

        other_user = self.create_org_user(
            'so-patcher@easyerp.local', full_name='Patcher User',
        )
        patch_resp = self.client.patch(
            f'/api/v1/sales/orders/{so_id}/',
            {'created_by': str(other_user.id), 'notes': 'updated'},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)

        so = SalesOrder.objects.get(id=so_id)
        self.assertEqual(so.created_by_id, self.operator.id)

    def test_null_created_by_order_lists_and_serializes_without_error(self):
        """Authorship: legacy/null created_by renders created_by_name as None."""
        SalesOrder.objects.create(
            customer=self.customer, organization=self.org, created_by=None,
        )
        list_resp = self.client.get('/api/v1/sales/orders/')
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)

        so = SalesOrder.objects.filter(created_by__isnull=True).first()
        detail_resp = self.client.get(f'/api/v1/sales/orders/{so.id}/')
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(detail_resp.data['created_by_name'])

    def test_invalid_transition_draft_to_fulfilled_returns_400(self):
        """S2: draft → fulfill (skipping confirmed) → 400."""
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=10,
            reason='test stock',
        )

        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 2,
                'unit_price': '25.00',
            },
        ])
        so_id = create_resp.data['id']

        fulfill_resp = self.client.post(
            f'/api/v1/sales/orders/{so_id}/fulfill/',
        )
        self.assertEqual(fulfill_resp.status_code, status.HTTP_400_BAD_REQUEST)


class SalesOrderFulfillmentTests(OrgTestMixin, TestCase):
    """S3: Fulfilling a sales order MUST decrement stock."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'so-fulfill@easyerp.local',
            full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.customer = Customer.objects.create(
            name='Big Buyer', tax_id='S3-TAX', organization=self.org,
        )
        self.product = Product.objects.create(
            sku='S3-SKU', name='Thing', cost='10', price='30',
            organization=self.org,
        )

    def _create_so(self, customer, line_items=None):
        data = {'customer': str(customer.id)}
        if line_items:
            data['line_items_write'] = line_items
        return self.client.post('/api/v1/sales/orders/', data, format='json')

    def test_fulfill_so_decrements_stock(self):
        """S3: Fulfilling decrements stock by line item quantities."""
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=50,
            reason='initial stock',
        )

        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 15,
                'unit_price': '30.00',
            },
        ])
        so_id = create_resp.data['id']

        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')

        level_before = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        self.assertEqual(level_before.quantity, 50)

        fulfill_resp = self.client.post(
            f'/api/v1/sales/orders/{so_id}/fulfill/',
        )
        self.assertEqual(fulfill_resp.status_code, status.HTTP_200_OK)

        level_after = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        self.assertEqual(level_after.quantity, 35)

    def test_fulfill_multiple_line_items_decrements_all(self):
        """S3: Multiple line items each decrement their warehoused stock."""
        product_b = Product.objects.create(
            sku='S3-B', name='Thing B', cost='5', price='15',
            organization=self.org,
        )

        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=30,
            reason='stock A',
        )
        inventory_services.add_stock(
            product_id=product_b.id,
            warehouse_id=self.warehouse.id,
            quantity=40,
            reason='stock B',
        )

        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 10, 'unit_price': '30.00',
            },
            {
                'product': str(product_b.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 15, 'unit_price': '15.00',
            },
        ])
        so_id = create_resp.data['id']

        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')

        level_a = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        level_b = StockLevel.objects.get(
            product=product_b, warehouse=self.warehouse,
        )
        self.assertEqual(level_a.quantity, 20)  # 30 - 10
        self.assertEqual(level_b.quantity, 25)  # 40 - 15

    def test_fulfill_unconfirmed_so_returns_400(self):
        """S3: Cannot fulfill a draft SO."""
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=10,
            reason='stock',
        )

        create_resp = self._create_so(self.customer, [
            {
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 3, 'unit_price': '30.00',
            },
        ])
        so_id = create_resp.data['id']

        fulfill_resp = self.client.post(
            f'/api/v1/sales/orders/{so_id}/fulfill/',
        )
        self.assertEqual(fulfill_resp.status_code, status.HTTP_400_BAD_REQUEST)

        level = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        self.assertEqual(level.quantity, 10)


class SalesOrderTotalPropertyTests(OrgTestMixin, TestCase):
    """`total` property: sum(quantity * unit_price) across line items."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(
            name='Total Customer', tax_id='TOTAL-TAX-001', organization=self.org,
        )
        self.product_a = Product.objects.create(
            sku='TOTAL-SKU-A', name='Widget A', cost='5', price='30',
            organization=self.org,
        )
        self.product_b = Product.objects.create(
            sku='TOTAL-SKU-B', name='Widget B', cost='5', price='15',
            organization=self.org,
        )

    def test_total_sums_line_items(self):
        """GIVEN a SO with two line items / WHEN reading `.total` / THEN it
        equals sum(quantity * unit_price) across all lines."""
        so = SalesOrder.objects.create(customer=self.customer, organization=self.org)
        so.line_items.create(
            product=self.product_a, quantity=3, unit_price=Decimal('30.00'),
            warehouse=self.warehouse,
        )
        so.line_items.create(
            product=self.product_b, quantity=2, unit_price=Decimal('15.00'),
            warehouse=self.warehouse,
        )
        self.assertEqual(so.total, Decimal('120.00'))

    def test_total_is_zero_with_no_line_items(self):
        """GIVEN a SO with no line items / WHEN reading `.total` / THEN it
        is zero (proves the sum over an empty queryset, not a stub)."""
        so = SalesOrder.objects.create(customer=self.customer, organization=self.org)
        self.assertEqual(so.total, Decimal('0'))


class SalesOrderApprovalGateTests(OrgTestMixin, TestCase):
    """Phase 2: confirm_so gate wiring + approve/reject actions (spec:
    Threshold gate blocks confirm above min_amount, Approver authority
    resolution, Unauthorized approval attempts are rejected)."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'approval-operator@easyerp.local', full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.customer = Customer.objects.create(
            name='Approval Customer', tax_id='APPROVAL-TAX-001', organization=self.org,
        )
        self.product = Product.objects.create(
            sku='APPROVAL-SKU-001', name='Gadget', cost='10', price='100',
            organization=self.org,
        )
        inventory_services.add_stock(
            product_id=self.product.id, warehouse_id=self.warehouse.id,
            quantity=100, reason='approval test stock',
        )

    def _create_so(self, quantity=10, unit_price='100.00'):
        resp = self.client.post('/api/v1/sales/orders/', {
            'customer': str(self.customer.id),
            'line_items_write': [{
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': quantity,
                'unit_price': unit_price,
            }],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        return resp.data['id']

    def test_confirm_without_rule_unaffected(self):
        """Zero-rules-configured: confirm proceeds unchanged, approval_status stays 'none'."""
        so_id = self._create_so()
        resp = self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'confirmed')
        self.assertEqual(resp.data['approval_status'], 'none')

    def test_confirm_over_threshold_blocks_and_returns_pending(self):
        """Order total (1000) >= min_amount (1000) -> confirm blocked, 200 + pending."""
        from core.models import ApprovalRule
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        so_id = self._create_so(quantity=10, unit_price='100.00')

        resp = self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'draft')
        self.assertEqual(resp.data['approval_status'], 'pending')

        so = SalesOrder.objects.get(id=so_id)
        self.assertEqual(so.status, 'draft')
        self.assertEqual(so.approval_status, 'pending')
        self.assertEqual(so.requested_by_id, self.operator.id)

    def test_approve_by_owner_completes_transition(self):
        """Owner approves a pending order -> approval_status='approved' and a
        subsequent confirm (auto re-invoked by the approve action) completes."""
        from core.models import ApprovalRule
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        so_id = self._create_so(quantity=10, unit_price='100.00')
        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')

        owner_membership = self.operator.memberships.get(organization=self.org)
        owner_membership.is_owner = True
        owner_membership.save()

        resp = self.client.post(f'/api/v1/sales/orders/{so_id}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['approval_status'], 'approved')
        self.assertEqual(resp.data['status'], 'confirmed')

        so = SalesOrder.objects.get(id=so_id)
        self.assertEqual(so.status, 'confirmed')
        self.assertEqual(so.approval_status, 'approved')
        self.assertEqual(so.approved_by_id, self.operator.id)
        self.assertIsNotNone(so.approved_at)

    def test_unauthorized_approve_returns_403(self):
        """A user matching none of the authority criteria gets 403 on approve."""
        from core.models import ApprovalRule, Role
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        so_id = self._create_so(quantity=10, unit_price='100.00')
        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')

        outsider_role = Role.objects.create(
            name='Outsider Role', organization=self.org, permissions={'sales': ['read']},
        )
        outsider = self.create_org_user(
            'approval-outsider@easyerp.local', full_name='Outsider', role=outsider_role,
        )
        outsider_client = APIClient()
        self._login(outsider_client, outsider)

        resp = outsider_client.post(f'/api/v1/sales/orders/{so_id}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        so = SalesOrder.objects.get(id=so_id)
        self.assertEqual(so.approval_status, 'pending')
