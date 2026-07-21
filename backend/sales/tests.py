"""
Phase 3 tests: Sales (S1, S2, S3).

Spec coverage:
  S1 — Customer CRUD with name, contact, tax_id
  S2 — Sales order lifecycle: draft → confirmed → fulfilled.
        Confirming with insufficient stock → 400.
  S3 — Fulfilling a sales order MUST decrement stock.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from inventory.models import Product, Warehouse, StockLevel
from sales.models import Customer, SalesOrder, SOLineItem
from inventory import services as inventory_services

User = get_user_model()


class CustomerCRUDTests(TestCase):
    """S1: Customer CRUD with name, contact, and tax ID."""

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
        Customer.objects.create(name='First', tax_id='C-TAX-001')
        response = self.client.post('/api/v1/sales/customers/', {
            'name': 'Second',
            'contact': 'Bob',
            'tax_id': 'C-TAX-001',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_customers(self):
        """S1: GET list → 200."""
        Customer.objects.create(name='A Client', tax_id='T-A')
        Customer.objects.create(name='B Client', tax_id='T-B')
        response = self.client.get('/api/v1/sales/customers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_retrieve_customer(self):
        """S1: GET detail → 200."""
        customer = Customer.objects.create(name='Target', tax_id='T-T')
        response = self.client.get(f'/api/v1/sales/customers/{customer.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Target')

    def test_viewer_cannot_create_customer(self):
        """S1: Viewer → 403 on create."""
        self._login_as(self.viewer)
        response = self.client.post('/api/v1/sales/customers/', {
            'name': 'Blocked', 'tax_id': 'T-BLOCK',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SalesOrderLifecycleTests(TestCase):
    """S2: SO lifecycle; confirming with insufficient stock → 400."""

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

        self.customer = Customer.objects.create(name='Test Customer', tax_id='SO-TAX-001')
        self.product = Product.objects.create(sku='SO-SKU-001', name='Gadget', cost='10', price='25')
        self.warehouse = Warehouse.objects.create(name='Sales WH')

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
        # Add stock first
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

        confirm_resp = self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
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
        fulfill_resp = self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')
        self.assertEqual(fulfill_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(fulfill_resp.data['status'], 'fulfilled')

    def test_confirm_with_insufficient_stock_returns_400(self):
        """S2: Confirming with not enough stock → 400."""
        # Only 3 in stock, SO wants 5
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

        confirm_resp = self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.assertEqual(confirm_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Insufficient stock', str(confirm_resp.data))

        # SO should still be draft
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

        confirm_resp = self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
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

        # Try confirming again
        reconfirm = self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.assertEqual(reconfirm.status_code, status.HTTP_400_BAD_REQUEST)

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

        fulfill_resp = self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')
        self.assertEqual(fulfill_resp.status_code, status.HTTP_400_BAD_REQUEST)


class SalesOrderFulfillmentTests(TestCase):
    """S3: Fulfilling a sales order MUST decrement stock."""

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

        self.customer = Customer.objects.create(name='Big Buyer', tax_id='S3-TAX')
        self.product = Product.objects.create(sku='S3-SKU', name='Thing', cost='10', price='30')
        self.warehouse = Warehouse.objects.create(name='Fulfillment WH')

    def _create_so(self, customer, line_items=None):
        data = {'customer': str(customer.id)}
        if line_items:
            data['line_items_write'] = line_items
        return self.client.post('/api/v1/sales/orders/', data, format='json')

    def test_fulfill_so_decrements_stock(self):
        """S3: Fulfilling decrements stock by line item quantities."""
        # Setup: add stock, create SO, confirm
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

        # Before fulfill: stock = 50
        level_before = StockLevel.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(level_before.quantity, 50)

        # Fulfill
        fulfill_resp = self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')
        self.assertEqual(fulfill_resp.status_code, status.HTTP_200_OK)

        # After fulfill: stock = 35
        level_after = StockLevel.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(level_after.quantity, 35)

    def test_fulfill_multiple_line_items_decrements_all(self):
        """S3: Multiple line items each decrement their warehoused stock."""
        product_b = Product.objects.create(sku='S3-B', name='Thing B', cost='5', price='15')

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
            {'product': str(self.product.id), 'warehouse': str(self.warehouse.id), 'quantity': 10, 'unit_price': '30.00'},
            {'product': str(product_b.id), 'warehouse': str(self.warehouse.id), 'quantity': 15, 'unit_price': '15.00'},
        ])
        so_id = create_resp.data['id']

        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')

        level_a = StockLevel.objects.get(product=self.product, warehouse=self.warehouse)
        level_b = StockLevel.objects.get(product=product_b, warehouse=self.warehouse)
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
            {'product': str(self.product.id), 'warehouse': str(self.warehouse.id), 'quantity': 3, 'unit_price': '30.00'},
        ])
        so_id = create_resp.data['id']

        # Try fulfilling without confirming first
        fulfill_resp = self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')
        self.assertEqual(fulfill_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Stock should be untouched
        level = StockLevel.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(level.quantity, 10)
