"""
Phase 1 — PR #1: SwitchOrgView + MeSerializer tests.

Spec coverage:
  A5 — User switches active org, gets fresh JWT with updated claim
  A4 — /users/me/ includes memberships array
"""

import json

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from core.models import Organization, Role, OrganizationMembership

User = get_user_model()


def _envelope(response):
    """Parse envelope-wrapped response body into {data, errors, meta}."""
    return json.loads(response.content)


# ---------------------------------------------------------------------------
# SwitchOrgView (spec A5)
# ---------------------------------------------------------------------------

class SwitchOrgViewTests(TestCase):
    """A5: Switch active organization via /auth/switch-org/."""

    def setUp(self):
        self.client = APIClient()

        # Create two orgs with roles
        self.org_a = Organization.objects.create(
            name='Org Alpha', tax_id='TAX-ALPHA',
        )
        self.role_a = Role.objects.create(
            name='Manager', organization=self.org_a,
            permissions={'core': ['read']},
        )
        self.org_b = Organization.objects.create(
            name='Org Beta', tax_id='TAX-BETA',
        )
        self.role_b = Role.objects.create(
            name='Viewer', organization=self.org_b,
            permissions={'core': ['read']},
        )
        self.org_c = Organization.objects.create(
            name='Org Gamma', tax_id='TAX-GAMMA',
        )
        self.role_c = Role.objects.create(
            name='Worker', organization=self.org_c,
            permissions={'core': ['read']},
        )

        # User with memberships in Org A and Org B
        self.user = User.objects.create_user(
            email='switch@easyerp.local',
            password='testpass123',
            full_name='Switch User',
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a,
            role=self.role_a, is_default=True,
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_b,
            role=self.role_b, is_default=False,
        )

    def _login(self):
        """Login and return access token."""
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'switch@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        return resp.data['access']

    def _switch_org(self, org_id, token=None):
        """POST /auth/switch-org/ and return the response."""
        if token:
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return self.client.post('/api/v1/auth/switch-org/', {
            'organization_id': str(org_id),
        }, format='json')

    def test_switch_to_valid_org_returns_new_tokens(self):
        """A5: Switching to org B returns 200 with access+refresh tokens."""
        token = self._login()
        response = self._switch_org(self.org_b.id, token)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_switch_to_valid_org_token_has_updated_claim(self):
        """A5: New access token carries active_organization_id for org B."""
        from rest_framework_simplejwt.tokens import AccessToken

        token = self._login()
        response = self._switch_org(self.org_b.id, token)

        access = response.data['access']
        decoded = AccessToken(access)
        self.assertEqual(decoded['active_organization_id'], str(self.org_b.id))

    def test_switch_to_non_member_org_returns_403(self):
        """A5: Switching to org C (not a member) → 403."""
        token = self._login()
        response = self._switch_org(self.org_c.id, token)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        body = _envelope(response)
        self.assertIsNone(body['data'])
        self.assertGreater(len(body['errors']), 0)
        error = body['errors'][0]
        self.assertEqual(error['code'], 'not_member')
        self.assertIn('No sos miembro', error['message'])

    def test_switch_to_same_org_returns_200(self):
        """A5: Switching to the already-active org A → 200 with new tokens."""
        token = self._login()
        response = self._switch_org(self.org_a.id, token)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_switch_org_requires_authentication(self):
        """A5: Unauthenticated request → 401."""
        response = self.client.post('/api/v1/auth/switch-org/', {
            'organization_id': str(self.org_a.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_switch_org_missing_organization_id_returns_400(self):
        """A5: POST without organization_id → 400."""
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.post('/api/v1/auth/switch-org/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# MeSerializer — /users/me/ with memberships (spec A4)
# ---------------------------------------------------------------------------

class MeSerializerTests(TestCase):
    """A4: /users/me/ response includes nested memberships array."""

    def setUp(self):
        self.client = APIClient()

        self.org = Organization.objects.create(
            name='Me Org', tax_id='TAX-ME-001',
        )
        self.role = Role.objects.create(
            name='Admin', organization=self.org,
            permissions={'core': ['admin']},
        )

        # User with one membership
        self.user = User.objects.create_user(
            email='me@easyerp.local',
            password='testpass123',
            full_name='Me User',
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org,
            role=self.role, is_default=True,
        )

    def _login(self):
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'me@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        return resp.data['access']

    def test_me_endpoint_includes_memberships_array(self):
        """A4: GET /users/me/ → response has 'memberships' key with nested data."""
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('memberships', response.data)

        memberships = response.data['memberships']
        self.assertIsInstance(memberships, list)
        self.assertEqual(len(memberships), 1)

    def test_me_membership_includes_organization(self):
        """A4: Each membership has an 'organization' sub-object."""
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/me/')

        membership = response.data['memberships'][0]
        self.assertIn('organization', membership)
        org = membership['organization']
        self.assertEqual(org['id'], str(self.org.id))
        self.assertEqual(org['name'], 'Me Org')
        self.assertEqual(org['tax_id'], 'TAX-ME-001')

    def test_me_membership_includes_role(self):
        """A4: Each membership has a 'role' sub-object with permissions."""
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/me/')

        membership = response.data['memberships'][0]
        self.assertIn('role', membership)
        role = membership['role']
        self.assertEqual(role['id'], str(self.role.id))
        self.assertEqual(role['name'], 'Admin')
        self.assertEqual(role['permissions'], {'core': ['admin']})

    def test_me_membership_includes_is_default(self):
        """A4: Each membership includes the 'is_default' flag."""
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/me/')

        membership = response.data['memberships'][0]
        self.assertTrue(membership['is_default'])

    def test_user_with_no_memberships_returns_empty_array(self):
        """A4/A7: User with zero memberships → memberships: []."""
        homeless = User.objects.create_user(
            email='homeless@easyerp.local',
            password='testpass123',
            full_name='No Org User',
        )
        resp = self.client.post('/api/v1/auth/login/', {
            'email': 'homeless@easyerp.local',
            'password': 'testpass123',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
        response = self.client.get('/api/v1/users/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('memberships', response.data)
        self.assertEqual(response.data['memberships'], [])

    def test_user_with_multiple_memberships_returns_all(self):
        """A4: User with 2 memberships → array length 2."""
        org2 = Organization.objects.create(
            name='Second Org', tax_id='TAX-ME-002',
        )
        role2 = Role.objects.create(
            name='Viewer', organization=org2,
            permissions={'inventory': ['read']},
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=org2,
            role=role2, is_default=False,
        )

        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['memberships']), 2)

    def test_me_endpoint_still_works_after_switch_org(self):
        """A4: /users/me/ still returns full memberships after switching orgs."""
        org2 = Organization.objects.create(
            name='Second Org', tax_id='TAX-ME-003',
        )
        role2 = Role.objects.create(
            name='Viewer', organization=org2,
            permissions={'inventory': ['read']},
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=org2,
            role=role2, is_default=False,
        )

        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # Switch to org2
        self.client.post('/api/v1/auth/switch-org/', {
            'organization_id': str(org2.id),
        }, format='json')

        # /users/me/ still returns both memberships
        response = self.client.get('/api/v1/users/me/')
        self.assertEqual(len(response.data['memberships']), 2)

    def test_me_endpoint_includes_user_fields(self):
        """A4: /users/me/ still includes base UserSerializer fields."""
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/v1/users/me/')

        self.assertIn('id', response.data)
        self.assertIn('email', response.data)
        self.assertIn('full_name', response.data)
        self.assertEqual(response.data['email'], 'me@easyerp.local')

    def test_admin_list_users_does_not_include_memberships(self):
        """Non-me actions should NOT expose memberships (admin list uses UserSerializer)."""
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # Admin listing users should NOT include memberships
        response = self.client.get('/api/v1/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The list wraps items in data[]
        body = _envelope(response)
        self.assertGreater(len(body['data']), 0)
        self.assertNotIn('memberships', body['data'][0])
