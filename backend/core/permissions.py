from rest_framework.permissions import BasePermission


# ============================================================================
# Legacy role-based permission classes (to be removed in Phase 6).
# ============================================================================

class IsAdmin(BasePermission):
    """Allow only users with the 'admin' role.

    .. deprecated:: Phase 2
        Replaced by ``OrgRolePermission``.  This class remains available
        for existing ViewSets and will be removed in Phase 6.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'admin'
        )


class IsOperator(BasePermission):
    """Allow users with 'admin' or 'operator' role.

    .. deprecated:: Phase 2
        Replaced by ``OrgRolePermission``.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ('admin', 'operator')
        )


class IsViewer(BasePermission):
    """Allow any authenticated user regardless of role.

    .. deprecated:: Phase 2
        Replaced by ``OrgRolePermission``.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
        )


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

    MODULES = {'inventory', 'purchasing', 'sales', 'invoicing'}
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

        # admin grants everything for this module (spec R4)
        if 'admin' in allowed_actions:
            return True

        # write implies read (spec R4)
        if self.action == 'read' and 'write' in allowed_actions:
            return True

        return self.action in allowed_actions

    # ------------------------------------------------------------------
    def has_object_permission(self, request, view, obj):
        """Object-level permission — delegates to ``has_permission`` for now.

        Phase 3 will add org-ownership checks on individual objects."""
        return self.has_permission(request, view)
