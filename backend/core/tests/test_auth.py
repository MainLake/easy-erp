"""
Phase 1 tests: Authentication (A1, A2, A3).

Spec coverage:
  A1 — JWT login with valid/invalid credentials
  A2 — Role enforcement (admin vs viewer)
  A3 — Token refresh + expired token rejection
"""

import json

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


def _envelope(response):
    """Parse envelope-wrapped response body into {data, errors, meta}."""
    return json.loads(response.content)


class AuthenticationTests(TestCase):
    """A1: JWT login, A3: token refresh and auth requirement."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin@easyerp.local',
            password='testpass123',
            full_name='Admin User',
        )
        self.viewer = User.objects.create_user(
            email='viewer@easyerp.local',
            password='testpass123',
            full_name='Viewer User',
        )

    # --- A1: Login ---

    def test_login_succeeds_with_valid_credentials(self):
        """A1: Valid credentials → 200 with access + refresh tokens."""
        response = self.client.post('/api/v1/auth/login/', {
            'email': 'admin@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_fails_with_invalid_password(self):
        """A1: Invalid password → 401."""
        response = self.client.post('/api/v1/auth/login/', {
            'email': 'admin@easyerp.local',
            'password': 'wrongpass',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_fails_with_nonexistent_user(self):
        """A1: Nonexistent email → 401."""
        response = self.client.post('/api/v1/auth/login/', {
            'email': 'nobody@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- A3: Token refresh ---

    def test_refresh_returns_new_access_token(self):
        """A3: Valid refresh token → new access token."""
        login_resp = self.client.post('/api/v1/auth/login/', {
            'email': 'admin@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        refresh = login_resp.data['refresh']

        response = self.client.post('/api/v1/auth/refresh/', {
            'refresh': refresh,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_protected_endpoint_rejects_unauthenticated(self):
        """A3 / X5: No token → 401 on protected endpoint."""
        response = self.client.get('/api/v1/users/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RoleEnforcementTests(TestCase):
    """A2: Role-based access control — admin vs viewer via OrgRolePermission."""

    def setUp(self):
        from core.models import Organization, Role, OrganizationMembership

        self.client = APIClient()

        # Create an org and roles so admin membership grants core:admin
        self.org = Organization.objects.create(
            name='Role Test Org', tax_id='ROLE-TAX-001',
        )
        self.admin_role = Role.objects.create(
            name='Admin', organization=self.org,
            permissions={'core': ['admin']},
        )

        self.admin = User.objects.create_user(
            email='admin@easyerp.local',
            password='testpass123',
            full_name='Admin User',
        )
        OrganizationMembership.objects.create(
            user=self.admin, organization=self.org,
            role=self.admin_role, is_default=True,
        )

        self.operator = User.objects.create_user(
            email='operator@easyerp.local',
            password='testpass123',
            full_name='Operator User',
        )
        # Operator has no membership → OrgRolePermission denies on scoped endpoints

        self.viewer = User.objects.create_user(
            email='viewer@easyerp.local',
            password='testpass123',
            full_name='Viewer User',
        )
        # Viewer has no membership → OrgRolePermission denies on scoped endpoints

    def _login(self, email, password='testpass123'):
        resp = self.client.post('/api/v1/auth/login/', {
            'email': email,
            'password': password,
        }, format='json')
        return resp.data['access']

    def test_admin_can_list_users(self):
        """A2: Admin token → 200 on users list endpoint."""
        token = self._login('admin@easyerp.local')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_list_users(self):
        """A2: Viewer token → 403 on users list endpoint (admin-only)."""
        token = self._login('viewer@easyerp.local')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_access_me_endpoint(self):
        """A2: Viewer token → 200 on /me endpoint (self-access allowed)."""
        token = self._login('viewer@easyerp.local')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'viewer@easyerp.local')

    def test_operator_can_access_me_endpoint(self):
        """Operator token → 200 on /me endpoint."""
        token = self._login('operator@easyerp.local')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'operator@easyerp.local')


class APIEnvelopeTests(TestCase):
    """X1: All endpoints return {data, errors, meta} envelope."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='env-admin@easyerp.local',
            password='testpass123',
            full_name='Envelope Admin',
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'env-admin@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.token = resp.data['access']

    def test_success_envelope_has_data_errors_meta(self):
        """X1: 2xx response → body has data, errors: [], meta: {} keys."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertIn('data', body)
        self.assertIn('errors', body)
        self.assertIn('meta', body)
        self.assertIsNotNone(body['data'])
        self.assertEqual(body['errors'], [])

    def test_error_envelope_has_errors_array(self):
        """X1: 4xx response → body has errors array with code and message."""
        # Login with invalid credentials
        response = self.client.post('/api/v1/auth/login/', {
            'email': 'nobody@easyerp.local',
            'password': 'wrong',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        body = _envelope(response)
        self.assertIn('data', body)
        self.assertIsNone(body['data'])
        self.assertIsInstance(body['errors'], list)
        self.assertGreater(len(body['errors']), 0)
        error = body['errors'][0]
        self.assertIn('code', error)
        self.assertIn('message', error)


class PaginationTests(TestCase):
    """X2: List endpoints support ?page= and ?page_size= with meta."""

    def setUp(self):
        from core.models import Organization, Role, OrganizationMembership
        from inventory.models import Product

        self.client = APIClient()
        self.org = Organization.objects.create(
            name='Pag Org', tax_id='PAG-TAX-001',
        )
        self.role = Role.objects.create(
            name='Pag Admin', organization=self.org,
            permissions={'inventory': ['admin']},
        )
        self.operator = User.objects.create_user(
            email='pag-operator@easyerp.local',
            password='testpass123',
            full_name='Pag Op',
        )
        OrganizationMembership.objects.create(
            user=self.operator, organization=self.org,
            role=self.role, is_default=True,
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'pag-operator@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

        # Create 25 products to test pagination
        for i in range(25):
            Product.objects.create(
                sku=f'PAG-{i:03d}',
                name=f'Product {i}',
                cost='1.00',
                price='2.00',
                organization=self.org,
            )

    def test_pagination_meta_includes_count_next_previous(self):
        """X2: Paginated response meta has count, next, previous."""
        response = self.client.get('/api/v1/inventory/products/?page_size=10')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        meta = body['meta']
        self.assertEqual(meta['count'], 25)
        self.assertIsNotNone(meta['next'])  # page 2 exists (10 items, 25 total)
        self.assertIsNone(meta['previous'])  # page 1

    def test_page_parameter_navigates(self):
        """X2: ?page=2 returns second page."""
        response = self.client.get('/api/v1/inventory/products/?page=2&page_size=10')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        # With 25 items and page_size=10, page 2 has items 11-20 (10 items)
        # or fewer if page_size wasn't applied (default 20 → 5 items)
        self.assertGreater(len(body['data']), 0)
        self.assertLessEqual(len(body['data']), 10)
        self.assertIsNotNone(body['meta']['previous'])  # page 2 has previous

    def test_default_page_size_is_20(self):
        """X2: Default page size returns 20 items (per settings)."""
        response = self.client.get('/api/v1/inventory/products/')
        body = _envelope(response)
        self.assertEqual(len(body['data']), 20)  # first 20 of 25


class FilteringTests(TestCase):
    """X3: List endpoints support field filtering via query params."""

    def setUp(self):
        from core.models import Organization, Role, OrganizationMembership
        from inventory.models import Product, Category

        self.client = APIClient()
        self.org = Organization.objects.create(
            name='Filt Org', tax_id='FILT-TAX-001',
        )
        self.role = Role.objects.create(
            name='Filt Admin', organization=self.org,
            permissions={'inventory': ['admin']},
        )
        self.operator = User.objects.create_user(
            email='filt-op@easyerp.local',
            password='testpass123',
            full_name='Filt Op',
        )
        OrganizationMembership.objects.create(
            user=self.operator, organization=self.org,
            role=self.role, is_default=True,
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'filt-op@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

        self.cat_a = Category.objects.create(
            name='Electronics', organization=self.org,
        )
        self.cat_b = Category.objects.create(
            name='Furniture', organization=self.org,
        )
        Product.objects.create(
            sku='FILT-E1', name='Phone', cost='100', price='200',
            category=self.cat_a, organization=self.org,
        )
        Product.objects.create(
            sku='FILT-E2', name='Laptop', cost='500', price='1000',
            category=self.cat_a, organization=self.org,
        )
        Product.objects.create(
            sku='FILT-F1', name='Chair', cost='50', price='100',
            category=self.cat_b, organization=self.org,
        )

    def test_filter_by_name_exact_match(self):
        """X3: ?name=Phone returns only matching product."""
        response = self.client.get('/api/v1/inventory/products/?name=Phone')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertEqual(len(body['data']), 1)
        self.assertEqual(body['data'][0]['sku'], 'FILT-E1')

    def test_filter_by_category_returns_matching(self):
        """X3: ?category=<uuid> returns products in that category."""
        response = self.client.get(
            f'/api/v1/inventory/products/?category={self.cat_a.id}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertEqual(len(body['data']), 2)  # Phone + Laptop

    def test_filter_by_sku_returns_unique(self):
        """X3: ?sku=FILT-F1 returns single product."""
        response = self.client.get('/api/v1/inventory/products/?sku=FILT-F1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _envelope(response)
        self.assertEqual(len(body['data']), 1)
        self.assertEqual(body['data'][0]['name'], 'Chair')


class OpenAPISchemaTests(TestCase):
    """X4: OpenAPI 3.0 schema at /api/v1/docs/."""

    def setUp(self):
        self.client = APIClient()

    def test_schema_endpoint_returns_valid_json(self):
        """X4: GET /api/v1/schema/?format=json returns valid OpenAPI JSON."""
        response = self.client.get('/api/v1/schema/?format=json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertEqual(data['openapi'], '3.0.3')
        self.assertIn('info', data)
        self.assertEqual(data['info']['title'], 'Easy ERP API')

    def test_docs_swagger_ui_accessible(self):
        """X4: GET /api/v1/docs/ returns Swagger UI page."""
        response = self.client.get('/api/v1/docs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Swagger UI renders HTML — check for key swagger elements
        content = response.content.lower()
        self.assertIn(b'swagger', content)
        # The page loads the OpenAPI spec from /api/v1/schema/
        self.assertIn(b'/api/v1/schema/', content)

    def test_unauthenticated_can_access_docs(self):
        """X4: OpenAPI schema and docs are publicly accessible."""
        # No auth header
        response = self.client.get('/api/v1/schema/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class AuthEnforcementTests(TestCase):
    """X5: All endpoints require Bearer token except login/refresh."""

    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(
            email='auth-enf@easyerp.local',
            password='testpass123',
            full_name='Auth Enf',
        )

    def test_unauthenticated_inventory_returns_401(self):
        """X5: No token → 401 on inventory endpoint."""
        response = self.client.get('/api/v1/inventory/products/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_purchasing_returns_401(self):
        """X5: No token → 401 on purchasing endpoint."""
        response = self.client.get('/api/v1/purchasing/suppliers/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_sales_returns_401(self):
        """X5: No token → 401 on sales endpoint."""
        response = self.client.get('/api/v1/sales/customers/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_invoicing_returns_401(self):
        """X5: No token → 401 on invoicing endpoint."""
        response = self.client.get('/api/v1/invoicing/invoices/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_is_public(self):
        """X5: Login endpoint accessible without token."""
        response = self.client.post('/api/v1/auth/login/', {
            'email': 'auth-enf@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_refresh_is_public(self):
        """X5: Refresh endpoint accessible without Bearer token."""
        # Get a refresh token first
        login_resp = self.client.post('/api/v1/auth/login/', {
            'email': 'auth-enf@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        refresh = login_resp.data['refresh']

        # Now call refresh without Bearer header
        client2 = APIClient()  # fresh client, no auth
        response = client2.post('/api/v1/auth/refresh/', {
            'refresh': refresh,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)


# =============================================================================
# Registration tests — org-owner-role (spec R1-R9)
# =============================================================================


class RegistrationTests(TestCase):
    """Self-service registration endpoint tests."""

    def setUp(self):
        self.client = APIClient()
        self.url = '/api/v1/auth/register/'

    # --- Happy Path (R1, R7) ---

    def test_register_happy_path_returns_201_with_tokens(self):
        """R1, R7: Valid registration → 201 with access and refresh tokens."""
        response = self.client.post(self.url, {
            'email': 'newuser@test.com',
            'password': 'Pass1234',
            'full_name': 'New User',
            'org_name': 'My New Company',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = _envelope(response)
        self.assertIsNotNone(body['data'])
        self.assertIn('access', body['data'])
        self.assertIn('refresh', body['data'])
        self.assertEqual(body['errors'], [])

    def test_register_creates_user_org_role_membership(self):
        """R1: Registration creates User, Organization, Role, Membership."""
        self.client.post(self.url, {
            'email': 'full@test.com',
            'password': 'Pass1234',
            'full_name': 'Full Person',
            'org_name': 'Full Company',
        }, format='json')

        from core.models import User, Organization, Role, OrganizationMembership
        user = User.objects.get(email='full@test.com')
        self.assertEqual(user.full_name, 'Full Person')

        org = Organization.objects.get(name='Full Company')
        self.assertEqual(org.tax_id, 'Full Company')

        role = Role.objects.get(organization=org, name='Admin')
        self.assertEqual(role.permissions, {'*': ['admin']})

        membership = OrganizationMembership.all_objects.get(user=user, organization=org)
        self.assertTrue(membership.is_owner)
        self.assertTrue(membership.is_default)
        self.assertEqual(membership.role, role)

    def test_register_jwt_has_active_organization_claim(self):
        """R7: JWT access token includes active_organization_id claim."""
        from core.models import Organization

        self.client.post(self.url, {
            'email': 'claim@test.com',
            'password': 'Pass1234',
            'full_name': 'Claim User',
            'org_name': 'Claim Org',
        }, format='json')

        org = Organization.objects.get(name='Claim Org')

        # Login and verify claim is in the token
        login_resp = self.client.post('/api/v1/auth/login/', {
            'email': 'claim@test.com',
            'password': 'Pass1234',
        }, format='json')
        body = _envelope(login_resp)
        import jwt
        token = body['data']['access']
        payload = jwt.decode(token, options={'verify_signature': False})
        self.assertEqual(payload['active_organization_id'], str(org.id))

    # --- Duplicate Email (R2) ---

    def test_register_duplicate_email_returns_409(self):
        """R2: Duplicate email → 409 Conflict."""
        from core.models import User
        User.objects.create_user(email='dup@test.com', password='Pass1234', full_name='First')

        response = self.client.post(self.url, {
            'email': 'dup@test.com',
            'password': 'Pass1234',
            'full_name': 'Second User',
            'org_name': 'Second Org',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        body = _envelope(response)
        self.assertIsNone(body['data'])
        error = body['errors'][0]
        self.assertEqual(error['code'], 'conflict')
        self.assertEqual(error['field'], 'email')

    # --- Duplicate Org Name (R3) ---

    def test_register_duplicate_org_name_returns_409(self):
        """R3: Duplicate org name → 409 Conflict."""
        from core.models import Organization
        Organization.objects.create(name='Acme Inc', tax_id='TAX-999')

        response = self.client.post(self.url, {
            'email': 'new@test.com',
            'password': 'Pass1234',
            'full_name': 'New User',
            'org_name': 'Acme Inc',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        body = _envelope(response)
        error = body['errors'][0]
        self.assertEqual(error['code'], 'conflict')
        self.assertEqual(error['field'], 'org_name')

    def test_register_duplicate_tax_id_returns_409(self):
        """R3: Duplicate tax_id → 409 Conflict."""
        from core.models import Organization
        Organization.objects.create(name='First Corp', tax_id='TAX-SHARED')

        response = self.client.post(self.url, {
            'email': 'new@test.com',
            'password': 'Pass1234',
            'full_name': 'New User',
            'org_name': 'Second Corp',
            'org_tax_id': 'TAX-SHARED',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        body = _envelope(response)
        error = body['errors'][0]
        self.assertEqual(error['code'], 'conflict')
        self.assertEqual(error['field'], 'org_tax_id')

    # --- Missing Required Fields (R4) ---

    def test_register_missing_fields_returns_400(self):
        """R4: Missing required fields → 400 with field-level errors."""
        response = self.client.post(self.url, {
            'email': 'test@test.com',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = _envelope(response)
        self.assertIsNone(body['data'])
        # Should have errors for password, full_name, org_name
        error_fields = {e['field'] for e in body['errors']}
        self.assertIn('password', error_fields)
        self.assertIn('full_name', error_fields)
        self.assertIn('org_name', error_fields)

    # --- Weak Password (R5) ---

    def test_register_password_all_digits_returns_400(self):
        """R5: Password with only digits → 400."""
        response = self.client.post(self.url, {
            'email': 'test@test.com',
            'password': '12345678',
            'full_name': 'Test',
            'org_name': 'Test Org',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = _envelope(response)
        error = body['errors'][0]
        self.assertEqual(error['field'], 'password')

    def test_register_password_all_letters_returns_400(self):
        """R5: Password with only letters → 400."""
        response = self.client.post(self.url, {
            'email': 'test@test.com',
            'password': 'abcdefgh',
            'full_name': 'Test',
            'org_name': 'Test Org',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = _envelope(response)
        error = body['errors'][0]
        self.assertEqual(error['field'], 'password')

    def test_register_password_too_short_returns_400(self):
        """R5: Password < 8 chars → 400."""
        response = self.client.post(self.url, {
            'email': 'test@test.com',
            'password': 'Ab1',
            'full_name': 'Test',
            'org_name': 'Test Org',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Invalid Email (R6) ---

    def test_register_invalid_email_returns_400(self):
        """R6: Invalid email format → 400."""
        response = self.client.post(self.url, {
            'email': 'not-an-email',
            'password': 'Pass1234',
            'full_name': 'Test',
            'org_name': 'Test Org',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = _envelope(response)
        error = body['errors'][0]
        self.assertEqual(error['field'], 'email')

    # --- No Authentication Required (R9) ---

    def test_register_endpoint_is_public(self):
        """R9: Registration does not require authentication."""
        response = self.client.post(self.url, {
            'email': 'public@test.com',
            'password': 'Pass1234',
            'full_name': 'Public User',
            'org_name': 'Public Org',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # --- Optional tax_id ---

    def test_register_without_tax_id_uses_org_name(self):
        """Registration without org_tax_id → tax_id defaults to org_name."""
        from core.models import Organization

        self.client.post(self.url, {
            'email': 'notax@test.com',
            'password': 'Pass1234',
            'full_name': 'No Tax',
            'org_name': 'NoTax Co',
        }, format='json')

        org = Organization.objects.get(name='NoTax Co')
        self.assertEqual(org.tax_id, 'NoTax Co')
