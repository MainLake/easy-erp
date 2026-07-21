"""
Phase 4 tests: Invoicing (B1, B2, B3).

Spec coverage:
  B1 — Invoice generation from fulfilled SO only. Non-fulfilled → 400.
  B2 — Credit and debit notes linked to an invoice.
  B3 — Invoice numbers MUST be sequential per legal entity.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from inventory.models import Product, Warehouse
from inventory import services as inventory_services
from sales.models import Customer, SalesOrder
from invoicing.models import Organization, Invoice, CreditDebitNote

User = get_user_model()


def _envelope(response):
    """Parse envelope-wrapped response body into {data, errors, meta}."""
    return json.loads(response.content)


class InvoiceGenerationTests(TestCase):
    """B1: Invoice generation from fulfilled SO only."""

    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(
            email='op-inv@easyerp.local',
            password='testpass123',
            full_name='Op Inv',
            role=User.Role.OPERATOR,
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'op-inv@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

        # Setup: org, product, warehouse, customer, SO
        self.org = Organization.objects.create(name='Test Org', tax_id='INV-TAX-001')
        self.product = Product.objects.create(
            sku='INV-SKU', name='Invoiceable', cost='10', price='25',
        )
        self.warehouse = Warehouse.objects.create(name='Inv WH')
        self.customer = Customer.objects.create(name='Inv Customer', tax_id='CUST-INV-001')

    def _create_fulfilled_so(self, quantity=5):
        """Helper: create and fulfill a sales order."""
        # Add stock
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=quantity + 5,
            reason='test stock',
        )

        # Create SO
        create_resp = self.client.post('/api/v1/sales/orders/', {
            'customer': str(self.customer.id),
            'line_items_write': [{
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': quantity,
                'unit_price': '25.00',
            }],
        }, format='json')
        so_id = create_resp.data['id']

        # Confirm + fulfill
        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')

        return so_id

    def _create_draft_so(self):
        """Helper: create a draft SO (not fulfilled)."""
        create_resp = self.client.post('/api/v1/sales/orders/', {
            'customer': str(self.customer.id),
            'line_items_write': [{
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 2,
                'unit_price': '25.00',
            }],
        }, format='json')
        return create_resp.data['id']

    # --- B1: Invoice generation ---

    def test_generate_invoice_from_fulfilled_so_succeeds(self):
        """B1: Generate invoice from fulfilled SO → 201 with sequential number."""
        so_id = self._create_fulfilled_so(quantity=3)
        response = self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('number', response.data)
        self.assertTrue(response.data['number'].startswith('INV-'))
        self.assertEqual(response.data['status'], 'issued')
        # Total should be 3 × 25 = 75
        self.assertEqual(str(response.data['total']), '75.00')

    def test_generate_invoice_from_draft_so_returns_400(self):
        """B1: Generating invoice from draft SO → 400."""
        so_id = self._create_draft_so()
        response = self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('errors', response.data)

    def test_generate_invoice_missing_sales_order_id_returns_400(self):
        """B1: Missing sales_order_id → 400."""
        response = self.client.post('/api/v1/invoicing/invoices/generate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('errors', response.data)

    def test_generate_invoice_nonexistent_so_returns_400(self):
        """B1: Nonexistent SO → 400."""
        response = self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': '00000000-0000-0000-0000-000000000000',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CreditDebitNoteTests(TestCase):
    """B2: Credit and debit notes linked to an invoice."""

    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(
            email='op-note@easyerp.local',
            password='testpass123',
            full_name='Op Note',
            role=User.Role.OPERATOR,
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'op-note@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

        self.org = Organization.objects.create(name='Note Org', tax_id='NOTE-TAX-001')
        self.product = Product.objects.create(sku='NOTE-SKU', name='Notable', cost='5', price='20')
        self.warehouse = Warehouse.objects.create(name='Note WH')
        self.customer = Customer.objects.create(name='Note Customer', tax_id='CUST-NOTE-001')

        # Create fulfilled SO and invoice
        inventory_services.add_stock(
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=10,
            reason='test stock',
        )
        so_resp = self.client.post('/api/v1/sales/orders/', {
            'customer': str(self.customer.id),
            'line_items_write': [{
                'product': str(self.product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': 4,
                'unit_price': '20.00',
            }],
        }, format='json')
        so_id = so_resp.data['id']
        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')

        inv_resp = self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id,
        }, format='json')
        self.invoice_id = inv_resp.data['id']
        self.invoice_number = inv_resp.data['number']

    def test_generate_credit_note_succeeds(self):
        """B2: Generate credit note → 201, linked to invoice."""
        response = self.client.post('/api/v1/invoicing/notes/generate_credit/', {
            'invoice_id': self.invoice_id,
            'amount': '100.00',
            'reason': 'Customer refund',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['type'], 'credit')
        self.assertEqual(str(response.data['amount']), '100.00')
        self.assertEqual(response.data['reason'], 'Customer refund')
        self.assertTrue(response.data['number'].startswith('CN-'))

    def test_generate_debit_note_succeeds(self):
        """B2: Generate debit note → 201, linked to invoice."""
        response = self.client.post('/api/v1/invoicing/notes/generate_debit/', {
            'invoice_id': self.invoice_id,
            'amount': '50.00',
            'reason': 'Additional charges',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['type'], 'debit')
        self.assertEqual(str(response.data['amount']), '50.00')
        self.assertTrue(response.data['number'].startswith('DN-'))

    def test_credit_note_linked_to_invoice(self):
        """B2: Credit note appears in invoice's notes list."""
        self.client.post('/api/v1/invoicing/notes/generate_credit/', {
            'invoice_id': self.invoice_id,
            'amount': '80.00',
            'reason': 'Discount',
        }, format='json')

        response = self.client.get(f'/api/v1/invoicing/invoices/{self.invoice_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['notes']), 1)
        self.assertEqual(response.data['notes'][0]['type'], 'credit')
        self.assertEqual(str(response.data['notes'][0]['amount']), '80.00')

    def test_generate_note_nonexistent_invoice_returns_400(self):
        """B2: Credit note for nonexistent invoice → 400."""
        response = self.client.post('/api/v1/invoicing/notes/generate_credit/', {
            'invoice_id': '00000000-0000-0000-0000-000000000000',
            'amount': '100.00',
            'reason': 'Test',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SequentialNumberingTests(TestCase):
    """B3: Invoice numbers MUST be sequential per legal entity."""

    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(
            email='op-seq@easyerp.local',
            password='testpass123',
            full_name='Op Seq',
            role=User.Role.OPERATOR,
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'op-seq@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

        self.org = Organization.objects.create(name='Seq Org', tax_id='SEQ-TAX-001')
        self.product = Product.objects.create(sku='SEQ-SKU', name='Sequential', cost='5', price='10')
        self.warehouse = Warehouse.objects.create(name='Seq WH')
        self.customer = Customer.objects.create(name='Seq Customer', tax_id='CUST-SEQ-001')

    def _create_fulfilled_so(self, sku, quantity=3):
        """Helper to create a fulfilled SO for invoicing."""
        product = Product.objects.create(sku=sku, name=f'Product {sku}', cost='5', price='10')
        inventory_services.add_stock(
            product_id=product.id,
            warehouse_id=self.warehouse.id,
            quantity=10,
            reason='test stock',
        )
        so_resp = self.client.post('/api/v1/sales/orders/', {
            'customer': str(self.customer.id),
            'line_items_write': [{
                'product': str(product.id),
                'warehouse': str(self.warehouse.id),
                'quantity': quantity,
                'unit_price': '10.00',
            }],
        }, format='json')
        so_id = so_resp.data['id']
        self.client.post(f'/api/v1/sales/orders/{so_id}/confirm/')
        self.client.post(f'/api/v1/sales/orders/{so_id}/fulfill/')
        return so_id, product

    def test_invoice_numbers_are_sequential(self):
        """B3: First invoice INV-001, second INV-002."""
        so_id_1, _ = self._create_fulfilled_so('SEQ-1')
        resp1 = self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id_1,
        }, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp1.data['number'], 'INV-001')

        so_id_2, _ = self._create_fulfilled_so('SEQ-2')
        resp2 = self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id_2,
        }, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp2.data['number'], 'INV-002')

    def test_credit_note_numbers_are_sequential(self):
        """B3: Credit note numbers CN-001, CN-002 are sequential."""
        so_id, _ = self._create_fulfilled_so('SEQ-CN')
        inv_resp = self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id,
        }, format='json')
        invoice_id = inv_resp.data['id']

        cn1 = self.client.post('/api/v1/invoicing/notes/generate_credit/', {
            'invoice_id': invoice_id, 'amount': '10.00', 'reason': 'First',
        }, format='json')
        self.assertEqual(cn1.data['number'], 'CN-001')

        cn2 = self.client.post('/api/v1/invoicing/notes/generate_credit/', {
            'invoice_id': invoice_id, 'amount': '20.00', 'reason': 'Second',
        }, format='json')
        self.assertEqual(cn2.data['number'], 'CN-002')

    def test_debit_note_numbers_are_sequential(self):
        """B3: Debit note numbers DN-001, DN-002 are sequential."""
        so_id, _ = self._create_fulfilled_so('SEQ-DN')
        inv_resp = self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id,
        }, format='json')
        invoice_id = inv_resp.data['id']

        dn1 = self.client.post('/api/v1/invoicing/notes/generate_debit/', {
            'invoice_id': invoice_id, 'amount': '15.00', 'reason': 'First',
        }, format='json')
        self.assertEqual(dn1.data['number'], 'DN-001')

        dn2 = self.client.post('/api/v1/invoicing/notes/generate_debit/', {
            'invoice_id': invoice_id, 'amount': '25.00', 'reason': 'Second',
        }, format='json')
        self.assertEqual(dn2.data['number'], 'DN-002')

    def test_org_invoice_number_increments_after_generation(self):
        """B3: Organization's last_invoice_number increments correctly."""
        self.assertEqual(self.org.last_invoice_number, 0)

        so_id, _ = self._create_fulfilled_so('SEQ-INC')
        self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id,
        }, format='json')

        self.org.refresh_from_db()
        self.assertEqual(self.org.last_invoice_number, 1)

    def test_invoice_list_endpoint_works(self):
        """B3: List invoices returns generated invoices."""
        so_id_1, _ = self._create_fulfilled_so('SEQ-L1')
        self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id_1,
        }, format='json')

        so_id_2, _ = self._create_fulfilled_so('SEQ-L2')
        self.client.post('/api/v1/invoicing/invoices/generate/', {
            'sales_order_id': so_id_2,
        }, format='json')

        response = self.client.get('/api/v1/invoicing/invoices/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertEqual(body['meta']['count'], 2)
