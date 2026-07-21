"""
Phase 3 tests: Purchasing (P1, P2, P3).

Spec coverage:
  P1 — Supplier CRUD with name, contact, tax_id
  P2 — PO lifecycle: draft → sent → received. Invalid transitions → 400.
  P3 — Receiving PO MUST increment stock for each line item.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from inventory.models import Product, Warehouse, StockLevel


def _envelope(response):
    """Parse envelope-wrapped response body into {data, errors, meta}."""
    return json.loads(response.content)
from purchasing.models import Supplier, PurchaseOrder, POLineItem

User = get_user_model()


class SupplierCRUDTests(TestCase):
    """P1: Supplier CRUD with name, contact, and tax ID."""

    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(
            email='operator@easyerp.local',
            password='testpass123',
            full_name='Operator User',
            role=User.Role.OPERATOR,
        )
        self.viewer = User.objects.create_user(
            email='viewer@easyerp.local',
            password='testpass123',
            full_name='Viewer User',
            role=User.Role.VIEWER,
        )
        self._login_as(self.operator)

    def _login_as(self, user, password='testpass123'):
        resp = self.client.post('/api/v1/auth/login/', {
            'email': user.email,
            'password': password,
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

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
        Supplier.objects.create(name='First', tax_id='TAX-001')
        response = self.client.post('/api/v1/purchasing/suppliers/', {
            'name': 'Second',
            'contact': 'Jane',
            'tax_id': 'TAX-001',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_suppliers(self):
        """P1: GET list → 200 with suppliers."""
        Supplier.objects.create(name='Alpha', tax_id='T-A')
        Supplier.objects.create(name='Beta', tax_id='T-B')
        response = self.client.get('/api/v1/purchasing/suppliers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertEqual(body['meta']['count'], 2)

    def test_retrieve_supplier(self):
        """P1: GET detail → 200."""
        supplier = Supplier.objects.create(name='Test Co', tax_id='T-C')
        response = self.client.get(f'/api/v1/purchasing/suppliers/{supplier.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tax_id'], 'T-C')

    def test_viewer_cannot_create_supplier(self):
        """P1: Viewer → 403 on create."""
        self._login_as(self.viewer)
        response = self.client.post('/api/v1/purchasing/suppliers/', {
            'name': 'Blocked', 'tax_id': 'T-BLOCK',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PurchaseOrderLifecycleTests(TestCase):
    """P2: PO lifecycle — draft → sent → received. Invalid transitions → 400."""

    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(
            email='operator@easyerp.local',
            password='testpass123',
            full_name='Operator User',
            role=User.Role.OPERATOR,
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'operator@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

        self.supplier = Supplier.objects.create(name='Acme Corp', tax_id='PO-TAX-001')
        self.product = Product.objects.create(sku='PO-SKU-001', name='Widget', cost='5', price='10')
        self.warehouse = Warehouse.objects.create(name='Main WH')

    def _create_po(self, supplier, line_items=None):
        data = {'supplier': str(supplier.id)}
        if line_items:
            data['line_items_write'] = line_items
        return self.client.post('/api/v1/purchasing/orders/', data, format='json')

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

        send_resp = self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        self.assertEqual(send_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(send_resp.data['status'], 'sent')

    def test_po_lifecycle_sent_to_received(self):
        """P2: sent → received transition succeeds."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 2, 'unit_cost': '3.00'},
        ])
        po_id = response.data['id']

        # Send first
        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')

        # Then receive
        receive_resp = self.client.post(f'/api/v1/purchasing/orders/{po_id}/receive/')
        self.assertEqual(receive_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(receive_resp.data['status'], 'received')

    def test_invalid_transition_received_to_sent_returns_400(self):
        """P2: received PO → send again → 400 (terminal state)."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '1.00'},
        ])
        po_id = response.data['id']

        # Send → Receive
        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        self.client.post(f'/api/v1/purchasing/orders/{po_id}/receive/')

        # Try sending a received PO
        send_again = self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        self.assertEqual(send_again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot transition', str(send_again.data))

    def test_invalid_transition_draft_to_received_returns_400(self):
        """P2: draft → receive (skipping sent) → 400."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '1.00'},
        ])
        po_id = response.data['id']

        receive_resp = self.client.post(f'/api/v1/purchasing/orders/{po_id}/receive/')
        self.assertEqual(receive_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot transition', str(receive_resp.data))

    def test_sending_already_sent_po_returns_400(self):
        """P2: sent → send (double send) → 400."""
        response = self._create_po(self.supplier, [
            {'product': str(self.product.id), 'quantity': 1, 'unit_cost': '1.00'},
        ])
        po_id = response.data['id']

        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        resend = self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        self.assertEqual(resend.status_code, status.HTTP_400_BAD_REQUEST)


class PurchaseOrderReceiptTests(TestCase):
    """P3: Receiving PO MUST increment stock for each line item."""

    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(
            email='operator@easyerp.local',
            password='testpass123',
            full_name='Operator User',
            role=User.Role.OPERATOR,
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'operator@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

        self.supplier = Supplier.objects.create(name='Parts Inc', tax_id='P3-TAX')
        self.product_a = Product.objects.create(sku='P3-A', name='Part A', cost='5', price='10')
        self.product_b = Product.objects.create(sku='P3-B', name='Part B', cost='8', price='15')
        self.warehouse = Warehouse.objects.create(name='Receiving WH')

    def test_receive_po_increments_stock(self):
        """P3: Receiving a PO creates stock levels matching line items."""
        # Create PO with 2 line items
        create_resp = self.client.post('/api/v1/purchasing/orders/', {
            'supplier': str(self.supplier.id),
            'line_items_write': [
                {'product': str(self.product_a.id), 'quantity': 10, 'unit_cost': '5.00'},
                {'product': str(self.product_b.id), 'quantity': 20, 'unit_cost': '8.00'},
            ],
        }, format='json')
        po_id = create_resp.data['id']

        # Verify no stock yet
        self.assertFalse(StockLevel.objects.filter(product=self.product_a).exists())
        self.assertFalse(StockLevel.objects.filter(product=self.product_b).exists())

        # Send → Receive
        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        receive_resp = self.client.post(f'/api/v1/purchasing/orders/{po_id}/receive/')
        self.assertEqual(receive_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(receive_resp.data['status'], 'received')

        # Verify stock was incremented
        # The service uses the first available warehouse (or creates default).
        # product_a should have 10, product_b should have 20.
        warehouse = Warehouse.objects.first()
        level_a = StockLevel.objects.get(product=self.product_a, warehouse=warehouse)
        level_b = StockLevel.objects.get(product=self.product_b, warehouse=warehouse)
        self.assertEqual(level_a.quantity, 10)
        self.assertEqual(level_b.quantity, 20)

    def test_receive_po_without_warehouse_auto_creates_default(self):
        """P3: Receiving with no warehouse auto-creates 'Default Warehouse'."""
        # Delete existing warehouse to test auto-creation
        Warehouse.objects.all().delete()

        create_resp = self.client.post('/api/v1/purchasing/orders/', {
            'supplier': str(self.supplier.id),
            'line_items_write': [
                {'product': str(self.product_a.id), 'quantity': 5, 'unit_cost': '5.00'},
            ],
        }, format='json')
        po_id = create_resp.data['id']

        self.client.post(f'/api/v1/purchasing/orders/{po_id}/send/')
        receive_resp = self.client.post(f'/api/v1/purchasing/orders/{po_id}/receive/')
        self.assertEqual(receive_resp.status_code, status.HTTP_200_OK)

        # Default warehouse should have been created
        default_wh = Warehouse.objects.get(name='Default Warehouse')
        level = StockLevel.objects.get(product=self.product_a, warehouse=default_wh)
        self.assertEqual(level.quantity, 5)
