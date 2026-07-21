"""
Core app tests — discovered automatically by pytest-django.

Provides OrgTestMixin: org-scoped fixtures for all test suites.

Usage (in any test class)::

    from core.tests import OrgTestMixin

    class MyTests(OrgTestMixin, TestCase):
        def setUp(self):
            super().setUp()
            self.user = self.create_org_user('test@easyerp.local')
            ...

The mixin creates:
  - self.org   (core.Organization)
  - self.role  (core.Role with full permissions)
  - self.branch (core.Branch)
  - self.warehouse (inventory.Warehouse)
  - self.create_org_user(email, ...) → User with membership

It also exposes self._full_permissions() and self._login(client, user).
"""

from django.contrib.auth import get_user_model

from core.models import (
    Organization,
    Branch,
    Role,
    OrganizationMembership,
    VALID_MODULES,
)
from inventory.models import Warehouse

User = get_user_model()


class OrgTestMixin:
    """Mixin providing org-scoped test fixtures.

    Call ``super().setUp()`` at the start of your test class's ``setUp``
    to create the default org, branch, warehouse, and admin role.
    """

    _ORG_COUNTER = 0

    def setUp(self):
        """Create default org, branch, warehouse, and admin role."""
        OrgTestMixin._ORG_COUNTER += 1
        n = OrgTestMixin._ORG_COUNTER
        self.org = Organization.objects.create(
            name=f'Test Org {n}',
            tax_id=f'TEST-ORG-{n:03d}',
        )
        self.role = Role.objects.create(
            name=f'Admin {n}',
            organization=self.org,
            permissions=self._full_permissions(),
        )
        self.branch = Branch.objects.create(
            name=f'Main Branch {n}',
            organization=self.org,
        )
        self.warehouse = Warehouse.objects.create(
            name=f'Main Warehouse {n}',
            organization=self.org,
        )
        # Ensure setUp chain works with mixins
        if hasattr(super(), 'setUp'):
            super().setUp()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _full_permissions():
        """Return a permissions dict granting admin on every module."""
        return {m: ['admin'] for m in VALID_MODULES}

    def create_org_user(
        self,
        email,
        password='testpass123',
        full_name='Test User',
        role=None,
        is_default=True,
    ):
        """Create a user with an OrganizationMembership to *self.org*.

        Returns the User instance.
        """
        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=self.org,
            role=role or self.role,
            is_default=is_default,
        )
        return user

    def _login(self, client, user, password='testpass123'):
        """Log in *user* on *client* and set the Bearer token."""
        resp = client.post('/api/v1/auth/login/', {
            'email': user.email,
            'password': password,
        }, format='json')
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
        return resp
