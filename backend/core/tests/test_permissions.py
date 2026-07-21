"""
Phase 2 tests: OrgRolePermission — dynamic RBAC (spec R3, R4, X3).

Covers the full allow / deny matrix for each module and action,
including the admin-implies-all and write-implies-read hierarchies.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from core.permissions import OrgRolePermission


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NO_USER = object()


def _make_request(org=None, permissions=None, user=_NO_USER):
    """Build a fake DRF request with ``user``, ``organization``, and a
    mock membership whose role carries *permissions*.

    Pass ``user=None`` to set ``request.user`` to ``None`` (simulating
    an absent user).  Omit *user* to get a default authenticated mock.
    """
    request = MagicMock()
    request.organization = org

    if user is _NO_USER:
        user = MagicMock()
        user.is_authenticated = True
    request.user = user

    # Only wire up the mock membership chain when user is a mock.
    if user is not None:
        membership = MagicMock()
        membership.role = MagicMock()
        membership.role.permissions = permissions or {}
        request.user.memberships.filter.return_value.select_related.return_value.first.return_value = (
            membership
        )
    return request


def _make_permission(module, action):
    """Instantiate OrgRolePermission with the given module and action."""
    return OrgRolePermission(module=module, action=action)


# ---------------------------------------------------------------------------
# Grant / deny matrix (spec R3, R4)
# ---------------------------------------------------------------------------

class OrgRolePermissionGrantTests(TestCase):
    """R3, R4: permission grants access when role has matching action."""

    MODULES = ['inventory', 'purchasing', 'sales', 'invoicing']
    ACTIONS = ['read', 'write', 'admin']

    # --- read action ---

    def test_read_granted_when_role_has_read(self):
        """R3: role has 'read' → read access granted."""
        for module in self.MODULES:
            perm = _make_permission(module, 'read')
            request = _make_request(
                org=MagicMock(),
                permissions={module: ['read']},
            )
            self.assertTrue(
                perm.has_permission(request, None),
                f'{module}:read should be granted when role has read',
            )

    def test_read_granted_when_role_has_write(self):
        """R4: role has 'write' → read is implied."""
        for module in self.MODULES:
            perm = _make_permission(module, 'read')
            request = _make_request(
                org=MagicMock(),
                permissions={module: ['write']},
            )
            self.assertTrue(
                perm.has_permission(request, None),
                f'{module}:read should be granted when role has write (write→read)',
            )

    def test_read_granted_when_role_has_admin(self):
        """R4: role has 'admin' → read granted (admin implies all)."""
        for module in self.MODULES:
            perm = _make_permission(module, 'read')
            request = _make_request(
                org=MagicMock(),
                permissions={module: ['admin']},
            )
            self.assertTrue(
                perm.has_permission(request, None),
                f'{module}:read should be granted when role has admin',
            )

    def test_read_denied_when_role_has_no_permissions(self):
        """R3: no permissions for module → read denied."""
        for module in self.MODULES:
            perm = _make_permission(module, 'read')
            request = _make_request(
                org=MagicMock(),
                permissions={},  # nothing at all
            )
            self.assertFalse(
                perm.has_permission(request, None),
                f'{module}:read should be denied with empty permissions',
            )

    def test_read_denied_when_only_other_module_permitted(self):
        """R3: sales:read role cannot read inventory."""
        perm = _make_permission('inventory', 'read')
        request = _make_request(
            org=MagicMock(),
            permissions={'sales': ['read', 'write']},
        )
        self.assertFalse(perm.has_permission(request, None))

    # --- write action ---

    def test_write_granted_when_role_has_write(self):
        """R3: role has 'write' → write access granted."""
        for module in self.MODULES:
            perm = _make_permission(module, 'write')
            request = _make_request(
                org=MagicMock(),
                permissions={module: ['write']},
            )
            self.assertTrue(
                perm.has_permission(request, None),
                f'{module}:write should be granted when role has write',
            )

    def test_write_granted_when_role_has_admin(self):
        """R4: role has 'admin' → write granted."""
        for module in self.MODULES:
            perm = _make_permission(module, 'write')
            request = _make_request(
                org=MagicMock(),
                permissions={module: ['admin']},
            )
            self.assertTrue(
                perm.has_permission(request, None),
                f'{module}:write should be granted when role has admin',
            )

    def test_write_denied_when_role_has_only_read(self):
        """R3: role has 'read' only → write denied."""
        for module in self.MODULES:
            perm = _make_permission(module, 'write')
            request = _make_request(
                org=MagicMock(),
                permissions={module: ['read']},
            )
            self.assertFalse(
                perm.has_permission(request, None),
                f'{module}:write should be denied when role has only read',
            )

    # --- admin action ---

    def test_admin_granted_when_role_has_admin(self):
        """R4: role has 'admin' → admin action granted."""
        for module in self.MODULES:
            perm = _make_permission(module, 'admin')
            request = _make_request(
                org=MagicMock(),
                permissions={module: ['admin']},
            )
            self.assertTrue(
                perm.has_permission(request, None),
                f'{module}:admin should be granted when role has admin',
            )

    def test_admin_denied_when_role_has_write_only(self):
        """R4: role has 'write' only → admin denied (write ≠ admin)."""
        for module in self.MODULES:
            perm = _make_permission(module, 'admin')
            request = _make_request(
                org=MagicMock(),
                permissions={module: ['write']},
            )
            self.assertFalse(
                perm.has_permission(request, None),
                f'{module}:admin should be denied when role has only write',
            )

    # --- Edge cases ---

    def test_permission_with_multiple_modules(self):
        """R3: role with inventory:write + sales:read — grants each correctly."""
        org = MagicMock()
        perms = {
            'inventory': ['write'],
            'sales': ['read'],
        }

        # inventory:read → implied by write
        self.assertTrue(
            _make_permission('inventory', 'read').has_permission(
                _make_request(org=org, permissions=perms), None,
            )
        )
        # inventory:write → direct
        self.assertTrue(
            _make_permission('inventory', 'write').has_permission(
                _make_request(org=org, permissions=perms), None,
            )
        )
        # inventory:admin → not granted
        self.assertFalse(
            _make_permission('inventory', 'admin').has_permission(
                _make_request(org=org, permissions=perms), None,
            )
        )
        # sales:read → direct
        self.assertTrue(
            _make_permission('sales', 'read').has_permission(
                _make_request(org=org, permissions=perms), None,
            )
        )
        # sales:write → denied
        self.assertFalse(
            _make_permission('sales', 'write').has_permission(
                _make_request(org=org, permissions=perms), None,
            )
        )


# ---------------------------------------------------------------------------
# Denial scenarios (no org / no membership / unauthenticated)
# ---------------------------------------------------------------------------

class OrgRolePermissionDenialTests(TestCase):
    """R3, X4: permission denies when context is missing."""

    def test_no_request_organization_denied(self):
        """X4: request.organization is None → denied (no active org)."""
        request = _make_request(org=None, permissions={'inventory': ['read']})
        perm = _make_permission('inventory', 'read')
        self.assertFalse(perm.has_permission(request, None))

    def test_no_membership_denied(self):
        """R3: user has no membership for active org → denied."""
        request = _make_request(
            org=MagicMock(),
            permissions={},
        )
        # Simulate no membership returned
        request.user.memberships.filter.return_value.select_related.return_value.first.return_value = None
        perm = _make_permission('inventory', 'read')
        self.assertFalse(perm.has_permission(request, None))

    def test_unauthenticated_denied(self):
        """R3: unauthenticated user → denied."""
        user = MagicMock()
        user.is_authenticated = False
        request = _make_request(
            user=user,
            org=MagicMock(),
            permissions={'inventory': ['admin']},
        )
        perm = _make_permission('inventory', 'read')
        self.assertFalse(perm.has_permission(request, None))

    def test_no_user_denied(self):
        """Request with user=None → denied."""
        request = _make_request(
            user=None,
            org=MagicMock(),
            permissions={'inventory': ['admin']},
        )
        perm = _make_permission('inventory', 'read')
        self.assertFalse(perm.has_permission(request, None))


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class OrgRolePermissionConstructorTests(TestCase):
    """Constructor rejects unknown modules and actions."""

    def test_unknown_module_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            OrgRolePermission(module='billing', action='read')
        self.assertIn('billing', str(ctx.exception))

    def test_unknown_action_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            OrgRolePermission(module='inventory', action='delete')
        self.assertIn('delete', str(ctx.exception))

    def test_known_modules_and_actions_accepted(self):
        for module in OrgRolePermission.MODULES:
            for action in OrgRolePermission.ACTIONS:
                perm = OrgRolePermission(module=module, action=action)
                self.assertEqual(perm.module, module)
                self.assertEqual(perm.action, action)


# ---------------------------------------------------------------------------
# Object-level permission
# ---------------------------------------------------------------------------

class OrgRolePermissionObjectTests(TestCase):
    """has_object_permission delegates to has_permission (Phase 2)."""

    def test_object_permission_delegates(self):
        perm = _make_permission('inventory', 'read')
        request = _make_request(
            org=MagicMock(),
            permissions={'inventory': ['read']},
        )
        self.assertTrue(perm.has_object_permission(request, None, None))

    def test_object_permission_denied_when_has_permission_denied(self):
        perm = _make_permission('inventory', 'write')
        request = _make_request(
            org=MagicMock(),
            permissions={'inventory': ['read']},
        )
        self.assertFalse(perm.has_object_permission(request, None, None))
