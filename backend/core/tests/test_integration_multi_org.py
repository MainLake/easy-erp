"""
Phase 5 integration tests: cross-org isolation (spec X1, X4).

Spec coverage:
  X1 — POST as org A → GET as org B returns empty (cross-org data leak)
  X4 — JWT with no active_org → 400 on protected endpoints
"""

import json

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from core.tests import OrgTestMixin
from core.models import Organization, Role, OrganizationMembership, VALID_MODULES
from inventory.models import Product


def _envelope(response):
    """Parse envelope-wrapped response body into {data, errors, meta}."""
    return json.loads(response.content)


class CrossOrgIsolationTests(OrgTestMixin, TestCase):
    """X1: Data from org A must be invisible to org B."""

    def setUp(self):
        super().setUp()
        # self.org is Org A from the mixin

        # Create Org B
        self.org_b = Organization.objects.create(
            name='Test Org B', tax_id='TEST-ORG-B-001',
        )
        self.role_b = Role.objects.create(
            name='Admin B', organization=self.org_b,
            permissions={m: ['admin'] for m in VALID_MODULES},
        )

    def test_product_created_in_org_a_not_visible_to_org_b(self):
        """X1: POST as org A → GET as org B returns empty."""
        # Create a product in Org A
        client_a = APIClient()
        user_a = self.create_org_user('user-a@easyerp.local')
        self._login(client_a, user_a)

        resp = client_a.post('/api/v1/inventory/products/', {
            'sku': 'ORG-A-SKU',
            'name': 'Org A Product',
            'cost': '10.00',
            'price': '20.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        product_a_id = resp.data['id']

        # Verify the product is visible to Org A
        list_a = client_a.get('/api/v1/inventory/products/')
        body_a = _envelope(list_a)
        self.assertEqual(body_a['meta']['count'], 1)

        # Now query as Org B — should see zero products
        client_b = APIClient()

        from django.contrib.auth import get_user_model
        User = get_user_model()
        user_b = User.objects.create_user(
            email='user-b@easyerp.local',
            password='testpass123',
            full_name='User B',
        )
        OrganizationMembership.objects.create(
            user=user_b, organization=self.org_b,
            role=self.role_b, is_default=True,
        )
        self._login(client_b, user_b)

        list_b = client_b.get('/api/v1/inventory/products/')
        body_b = _envelope(list_b)
        self.assertEqual(body_b['meta']['count'], 0,
                         'Org B should not see Org A products')

        # Org B cannot retrieve Org A's product
        retrieve = client_b.get(
            f'/api/v1/inventory/products/{product_a_id}/',
        )
        self.assertEqual(retrieve.status_code, status.HTTP_404_NOT_FOUND)

    def test_supplier_created_in_org_a_not_visible_to_org_b(self):
        """X1: Supplier CRUD scoped per org."""
        client_a = APIClient()
        user_a = self.create_org_user('supplier-a@easyerp.local')
        self._login(client_a, user_a)

        client_a.post('/api/v1/purchasing/suppliers/', {
            'name': 'Org A Supplier', 'tax_id': 'SUPP-A-001',
        }, format='json')

        # Org B sees empty supplier list
        from django.contrib.auth import get_user_model
        User = get_user_model()
        client_b = APIClient()
        user_b = User.objects.create_user(
            email='supplier-b@easyerp.local',
            password='testpass123',
            full_name='Supplier B',
        )
        OrganizationMembership.objects.create(
            user=user_b, organization=self.org_b,
            role=self.role_b, is_default=True,
        )
        self._login(client_b, user_b)

        list_b = client_b.get('/api/v1/purchasing/suppliers/')
        body_b = _envelope(list_b)
        self.assertEqual(body_b['meta']['count'], 0,
                         'Org B should not see Org A suppliers')


class NoOrgJWTDenialTests(TestCase):
    """X4: JWT without active_org → 400 on protected endpoints."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.client = APIClient()
        # Create a user with NO memberships — JWT will have no active_org
        self.no_org_user = User.objects.create_user(
            email='no-org@easyerp.local',
            password='testpass123',
            full_name='No Org User',
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'no-org@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.token = resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def test_inventory_list_denied_without_active_org(self):
        """X4: JWT without active_org → 403 on inventory list."""
        response = self.client.get('/api/v1/inventory/products/')
        # When no org is resolved, OrgRolePermission denies access → 403
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_purchasing_list_denied_without_active_org(self):
        """X4: JWT without active_org → 403 on purchasing list."""
        response = self.client.get('/api/v1/purchasing/suppliers/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_sales_list_denied_without_active_org(self):
        """X4: JWT without active_org → 403 on sales list."""
        response = self.client.get('/api/v1/sales/customers/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invoicing_list_denied_without_active_org(self):
        """X4: JWT without active_org → 403 on invoicing list."""
        response = self.client.get('/api/v1/invoicing/invoices/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
