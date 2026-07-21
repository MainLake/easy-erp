from rest_framework.permissions import BasePermission

from .models import OrganizationMembership


# ============================================================================
# OrgRolePermission — dynamic, multi-tenant, org-aware RBAC (spec R3, R4, X3)
# ============================================================================

class OrgRolePermission(BasePermission):
    """Grant/deny access based on the user's role in the active organization.

    Usage::

        permission_classes = [OrgRolePermission('inventory', 'write')]

    The permission reads the user's membership for
    ``request.organization`` (set by ``OrganizationMiddleware``) and
    checks whether the membership's role grants the required *action*
    for the given *module*.

    **Hierarchy (spec R4)**

    - ``admin``  → grants every action on the module
    - ``write``  → grants create / update / partial_update / destroy
      *and* implies ``read``
    - ``read``   → grants list / retrieve only
    """

    MODULES = {'core', 'inventory', 'purchasing', 'sales', 'invoicing'}
    ACTIONS = {'read', 'write', 'admin'}

    # ------------------------------------------------------------------
    def __init__(self, module, action):
        if module not in self.MODULES:
            raise ValueError(
                f'Unknown module "{module}". Valid: {sorted(self.MODULES)}'
            )
        if action not in self.ACTIONS:
            raise ValueError(
                f'Unknown action "{action}". Valid: {sorted(self.ACTIONS)}'
            )
        self.module = module
        self.action = action

    # ------------------------------------------------------------------
    def has_permission(self, request, view):
        # Not authenticated → DRF's IsAuthenticated handles 401 before we run.
        if not request.user or not request.user.is_authenticated:
            return False

        org = getattr(request, 'organization', None)
        if org is None:
            # No active org resolved — middleware didn't find one.
            return False

        membership = (
            request.user.memberships
            .filter(organization=org)
            .select_related('role')
            .first()
        )
        if membership is None:
            return False

        allowed_actions = membership.role.permissions.get(self.module, [])

        # Wildcard "*" module grants permissions on every module (spec R8).
        wildcard_actions = membership.role.permissions.get('*', [])
        if 'admin' in wildcard_actions:
            return True
        if self.action == 'read' and 'write' in wildcard_actions:
            return True
        if self.action in wildcard_actions:
            return True

        # admin grants everything for this module (spec R4)
        if 'admin' in allowed_actions:
            return True

        # write implies read (spec R4)
        if self.action == 'read' and 'write' in allowed_actions:
            return True

        return self.action in allowed_actions

    # ------------------------------------------------------------------
    def has_object_permission(self, request, view, obj):
        """Object-level permission — delegates to ``has_permission``.

        Org-ownership checks happen through the org-scoped manager
        that auto-filters querysets by the request organization."""
        return self.has_permission(request, view)


# ============================================================================
# IsOrgOwner — owner-only guard for org management (spec O5)
# ============================================================================


class IsOrgOwner(BasePermission):
    """Grant access only to organization owners.

    Checks that the authenticated user has an ``is_owner=True`` membership
    for the active organization (``request.organization``, set by the
    ``OrganizationMiddleware``).

    Usage::

        permission_classes = [IsOrgOwner]

    The permission is additive — combine with ``OrgRolePermission`` for
    endpoints that need both ownership AND a specific role action.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        org = getattr(request, 'organization', None)
        if org is None:
            return False

        return OrganizationMembership.all_objects.filter(
            user=request.user,
            organization=org,
            is_owner=True,
        ).exists()
