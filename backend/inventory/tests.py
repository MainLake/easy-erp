"""
Phase 2 tests: Inventory (I1, I2, I3).

Spec coverage:
  I1 — Product CRUD with unique SKU; duplicate SKU → 400; per-org SKU uniqueness
  I2 — Stock levels per product per warehouse; negative guard
  I3 — Stock movements: add, remove, transfer
"""

import json
import uuid

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from core.tests import OrgTestMixin
from core.models import Role, OrganizationMembership, Organization
from inventory.models import Category, Product, Warehouse, StockLevel, StockMovement


def _envelope(response):
    """Parse envelope-wrapped response body into {data, errors, meta}."""
    return json.loads(response.content)


class ProductCRUDTests(OrgTestMixin, TestCase):
    """I1: Product CRUD with unique SKU enforcement."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'operator-inv@easyerp.local',
            full_name='Operator User',
        )
        self.viewer_role = Role.objects.create(
            name='Viewer',
            organization=self.org,
            permissions={'inventory': ['read']},
        )
        self.viewer = self.create_org_user(
            'viewer-inv@easyerp.local',
            full_name='Viewer User',
            role=self.viewer_role,
        )
        self._login(self.client, self.operator)

    # --- Create ---

    def test_create_product_succeeds(self):
        """I1: POST with valid fields → 201 with product resource."""
        response = self.client.post('/api/v1/inventory/products/', {
            'sku': 'WIDGET-001',
            'name': 'Standard Widget',
            'cost': '5.50',
            'price': '12.99',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['sku'], 'WIDGET-001')
        self.assertEqual(response.data['name'], 'Standard Widget')

    def test_create_product_duplicate_sku_returns_400(self):
        """I1: Duplicate SKU in same org → 400."""
        Product.objects.create(
            sku='WIDGET-001', name='First', organization=self.org,
        )
        response = self.client.post('/api/v1/inventory/products/', {
            'sku': 'WIDGET-001',
            'name': 'Second Widget',
            'cost': '6.00',
            'price': '15.00',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = response.data.get('errors', [])
        self.assertTrue(any(e.get('field') == 'sku' for e in errors))

    def test_create_product_missing_required_fields_returns_400(self):
        """I1: Missing required fields → 400."""
        response = self.client.post('/api/v1/inventory/products/', {
            'sku': 'ONLY-SKU',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Read ---

    def test_list_products(self):
        """I1: GET list → 200 with all org-scoped products."""
        Product.objects.create(
            sku='A-1', name='Alpha', cost='1.00', price='2.00',
            organization=self.org,
        )
        Product.objects.create(
            sku='B-1', name='Beta', cost='3.00', price='4.00',
            organization=self.org,
        )
        response = self.client.get('/api/v1/inventory/products/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertEqual(body['meta']['count'], 2)

    def test_retrieve_product(self):
        """I1: GET detail → 200 with product data."""
        product = Product.objects.create(
            sku='A-1', name='Alpha', cost='1.00', price='2.00',
            organization=self.org,
        )
        response = self.client.get(f'/api/v1/inventory/products/{product.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['sku'], 'A-1')

    # --- Update ---

    def test_update_product(self):
        """I1: PATCH → 200 with updated fields."""
        product = Product.objects.create(
            sku='OLD', name='Old Name', cost='1.00', price='2.00',
            organization=self.org,
        )
        response = self.client.patch(
            f'/api/v1/inventory/products/{product.id}/',
            {'name': 'New Name', 'price': '15.00'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'New Name')
        self.assertEqual(response.data['price'], '15.00')

    # --- Delete ---

    def test_delete_product(self):
        """I1: DELETE → 204."""
        product = Product.objects.create(
            sku='GONE', name='To Delete', cost='0', price='0',
            organization=self.org,
        )
        response = self.client.delete(f'/api/v1/inventory/products/{product.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Product.objects.filter(id=product.id).exists())

    # --- Role: viewer can read, cannot write ---

    def test_viewer_can_list_products(self):
        """I1: Viewer → 200 on list."""
        viewer_client = APIClient()
        self._login(viewer_client, self.viewer)
        response = viewer_client.get('/api/v1/inventory/products/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_product(self):
        """I1: Viewer → 403 on create."""
        viewer_client = APIClient()
        self._login(viewer_client, self.viewer)
        response = viewer_client.post('/api/v1/inventory/products/', {
            'sku': 'V-001', 'name': 'Viewer Product',
            'cost': '1.00', 'price': '2.00',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class StockLevelTests(OrgTestMixin, TestCase):
    """I2: Stock levels per product per warehouse; negative guard."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'stock-op@easyerp.local',
            full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.product = Product.objects.create(
            sku='STOCK-TEST', name='Stock Test', cost='10', price='20',
            organization=self.org,
        )

    def _add_stock(self, product, warehouse, quantity, reason='test setup'):
        """Helper: call add-stock endpoint."""
        return self.client.post(
            f'/api/v1/inventory/products/{product.id}/add-stock/',
            {
                'warehouse_id': str(warehouse.id),
                'quantity': quantity,
                'reason': reason,
            },
            format='json',
        )

    def test_stock_levels_endpoint_returns_stock(self):
        """I2: GET /stock/ returns stock levels."""
        self._add_stock(self.product, self.warehouse, 10)
        response = self.client.get('/api/v1/inventory/products/stock/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        results = body['data']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['quantity'], 10)

    def test_add_stock_increments_level(self):
        """I2: Adding stock increases quantity."""
        self._add_stock(self.product, self.warehouse, 10)
        level = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        self.assertEqual(level.quantity, 10)

        self._add_stock(self.product, self.warehouse, 5)
        level.refresh_from_db()
        self.assertEqual(level.quantity, 15)

    def test_remove_stock_rejects_negative_quantity(self):
        """I2: Removing more stock than available → 400."""
        self._add_stock(self.product, self.warehouse, 3)

        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/remove-stock/',
            {
                'warehouse_id': str(self.warehouse.id),
                'quantity': 5,
                'reason': 'overdraft attempt',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        level = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        self.assertEqual(level.quantity, 3)

    def test_remove_stock_succeeds(self):
        """I2: Removing available stock → 200 and stock decreases."""
        self._add_stock(self.product, self.warehouse, 10)

        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/remove-stock/',
            {
                'warehouse_id': str(self.warehouse.id),
                'quantity': 4,
                'reason': 'order fulfillment',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        level = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        self.assertEqual(level.quantity, 6)

    def test_add_stock_zero_quantity_rejected(self):
        """I2: Adding zero quantity → 400."""
        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/add-stock/',
            {
                'warehouse_id': str(self.warehouse.id),
                'quantity': 0,
                'reason': 'zero test',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StockMovementTests(OrgTestMixin, TestCase):
    """I3: Stock movements — add, remove, transfer."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            'move-op@easyerp.local',
            full_name='Operator User',
        )
        self._login(self.client, self.operator)

        self.product = Product.objects.create(
            sku='MOVE-TEST', name='Movement Test', cost='5', price='10',
            organization=self.org,
        )
        self.wh_b = Warehouse.objects.create(
            name='Warehouse B', organization=self.org,
        )

    def _add_stock(self, product, warehouse, quantity, reason='test'):
        return self.client.post(
            f'/api/v1/inventory/products/{product.id}/add-stock/',
            {
                'warehouse_id': str(warehouse.id),
                'quantity': quantity,
                'reason': reason,
            },
            format='json',
        )

    def test_add_stock_creates_movement(self):
        """I3: add_stock creates a StockMovement with type=add."""
        response = self._add_stock(
            self.product, self.warehouse, 10, reason='initial stock',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        movement = StockMovement.objects.get()
        self.assertEqual(movement.movement_type, StockMovement.MovementType.ADD)
        self.assertEqual(movement.quantity, 10)
        self.assertEqual(movement.reason, 'initial stock')

    def test_remove_stock_creates_movement(self):
        """I3: remove_stock creates a StockMovement with type=remove."""
        self._add_stock(self.product, self.warehouse, 10)

        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/remove-stock/',
            {
                'warehouse_id': str(self.warehouse.id),
                'quantity': 3,
                'reason': 'customer order',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            StockMovement.objects.filter(movement_type='remove').count(), 1,
        )

    def test_transfer_stock_updates_both_warehouses(self):
        """I3: Transfer moves stock from A to B."""
        self._add_stock(self.product, self.warehouse, 10)

        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/transfer-stock/',
            {
                'from_warehouse_id': str(self.warehouse.id),
                'to_warehouse_id': str(self.wh_b.id),
                'quantity': 4,
                'reason': 'rebalancing',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        a_level = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        b_level = StockLevel.objects.get(
            product=self.product, warehouse=self.wh_b,
        )
        self.assertEqual(a_level.quantity, 6)
        self.assertEqual(b_level.quantity, 4)

        self.assertEqual(
            StockMovement.objects.filter(movement_type='transfer_out').count(), 1,
        )
        self.assertEqual(
            StockMovement.objects.filter(movement_type='transfer_in').count(), 1,
        )

    def test_transfer_stock_insufficient_quantity_rejected(self):
        """I3: Transfer with insufficient stock → 400, no data mutated."""
        self._add_stock(self.product, self.warehouse, 3)

        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/transfer-stock/',
            {
                'from_warehouse_id': str(self.warehouse.id),
                'to_warehouse_id': str(self.wh_b.id),
                'quantity': 10,
                'reason': 'overdraft',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        a_level = StockLevel.objects.get(
            product=self.product, warehouse=self.warehouse,
        )
        self.assertEqual(a_level.quantity, 3)
        self.assertFalse(
            StockLevel.objects.filter(
                product=self.product, warehouse=self.wh_b,
            ).exists(),
        )

    def test_transfer_to_same_warehouse_rejected(self):
        """I3: Transfer from and to the same warehouse → 400."""
        self._add_stock(self.product, self.warehouse, 10)

        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/transfer-stock/',
            {
                'from_warehouse_id': str(self.warehouse.id),
                'to_warehouse_id': str(self.warehouse.id),
                'quantity': 2,
                'reason': 'same warehouse',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_movement_audit_trail_readable(self):
        """I3: Movements endpoint exposes full audit trail."""
        self._add_stock(self.product, self.warehouse, 10, reason='setup')

        response = self.client.get('/api/v1/inventory/movements/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        results = body['data']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['movement_type'], 'add')


# ---------------------------------------------------------------------------
# 404 safety for missing/cross-org references (fix-audit-findings — Phase 2)
# ---------------------------------------------------------------------------

class StockMutation404SafetyTests(OrgTestMixin, TestCase):
    """Spec: Safe 404 for Missing/Cross-Org References.

    add_stock/remove_stock/transfer_stock must return a 404 in the
    standard envelope for unknown or cross-org product/warehouse ids,
    never an unhandled 500.
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.operator = self.create_org_user(
            '404-op@easyerp.local',
            full_name='404 Operator',
        )
        self._login(self.client, self.operator)

        self.product = Product.objects.create(
            sku='404-TEST', name='404 Test', cost='1', price='2',
            organization=self.org,
        )
        self.unknown_id = uuid.uuid4()

        # A second, unrelated org + warehouse for cross-org tests.
        self.other_org = Organization.objects.create(
            name='Other Org 404', tax_id='OTHER-ORG-404',
        )
        self.foreign_warehouse = Warehouse.objects.create(
            name='Foreign Warehouse', organization=self.other_org,
        )

    def test_add_stock_unknown_product_returns_404_envelope(self):
        """Unknown product_id → HTTP 404 in {data,errors,meta} envelope."""
        response = self.client.post(
            f'/api/v1/inventory/products/{self.unknown_id}/add-stock/',
            {
                'warehouse_id': str(self.warehouse.id),
                'quantity': 5,
                'reason': 'unknown product',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = _envelope(response)
        self.assertIsNone(body['data'])
        self.assertTrue(len(body['errors']) >= 1)
        self.assertEqual(body['errors'][0]['code'], 'not_found')

    def test_add_stock_cross_org_warehouse_returns_404_envelope(self):
        """Warehouse belonging to a different org → HTTP 404 envelope."""
        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/add-stock/',
            {
                'warehouse_id': str(self.foreign_warehouse.id),
                'quantity': 5,
                'reason': 'cross-org warehouse',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = _envelope(response)
        self.assertIsNone(body['data'])
        self.assertEqual(body['errors'][0]['code'], 'not_found')

    def test_remove_stock_unknown_product_returns_404_envelope(self):
        response = self.client.post(
            f'/api/v1/inventory/products/{self.unknown_id}/remove-stock/',
            {
                'warehouse_id': str(self.warehouse.id),
                'quantity': 1,
                'reason': 'unknown product',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = _envelope(response)
        self.assertIsNone(body['data'])
        self.assertEqual(body['errors'][0]['code'], 'not_found')

    def test_transfer_stock_cross_org_to_warehouse_returns_404_envelope(self):
        """Unknown to_warehouse_id in transfer → HTTP 404 envelope."""
        self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/add-stock/',
            {'warehouse_id': str(self.warehouse.id), 'quantity': 10, 'reason': 'setup'},
            format='json',
        )
        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/transfer-stock/',
            {
                'from_warehouse_id': str(self.warehouse.id),
                'to_warehouse_id': str(self.unknown_id),
                'quantity': 1,
                'reason': 'unknown destination',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = _envelope(response)
        self.assertIsNone(body['data'])
        self.assertEqual(body['errors'][0]['code'], 'not_found')

    def test_add_stock_valid_same_org_ids_still_succeeds(self):
        """Regression guard: valid same-org product/warehouse ids still work."""
        response = self.client.post(
            f'/api/v1/inventory/products/{self.product.id}/add-stock/',
            {
                'warehouse_id': str(self.warehouse.id),
                'quantity': 7,
                'reason': 'regression check',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        level = StockLevel.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(level.quantity, 7)
