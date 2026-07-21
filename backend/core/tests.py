"""
Phase 1 tests: Authentication (A1, A2, A3).

Spec coverage:
  A1 — JWT login with valid/invalid credentials
  A2 — Role enforcement (admin vs viewer)
  A3 — Token refresh + expired token rejection
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class AuthenticationTests(TestCase):
    """A1: JWT login, A3: token refresh and auth requirement."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin@easyerp.local',
            password='testpass123',
            full_name='Admin User',
            role=User.Role.ADMIN,
        )
        self.viewer = User.objects.create_user(
            email='viewer@easyerp.local',
            password='testpass123',
            full_name='Viewer User',
            role=User.Role.VIEWER,
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
    """A2: Role-based access control — admin vs viewer."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin@easyerp.local',
            password='testpass123',
            full_name='Admin User',
            role=User.Role.ADMIN,
        )
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
