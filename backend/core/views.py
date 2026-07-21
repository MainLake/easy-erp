from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Branch, Organization, OrganizationMembership, Role, User
from .serializers import (
    BranchSerializer,
    OrganizationMembershipSerializer,
    OrganizationSerializer,
    RoleSerializer,
    UserSerializer,
)
from .permissions import OrgRolePermission


class UserViewSet(viewsets.ModelViewSet):
    """Manage users — admin-only CRUD, plus self-serve /me endpoint.

    Admin-only CRUD requires ``core:admin`` in the user's membership
    role.  The self-serve ``/me`` endpoint only requires authentication.
    """

    queryset = User.objects.all().order_by('-created_at')
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action == 'me':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), OrgRolePermission('core', 'admin')]

    @action(
        detail=False,
        methods=['get', 'patch'],
        permission_classes=[permissions.IsAuthenticated],
    )
    def me(self, request):
        """Return (GET) or update (PATCH) the currently authenticated user."""
        user = request.user
        if request.method == 'PATCH':
            serializer = self.get_serializer(user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        serializer = self.get_serializer(user)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Multi-org ViewSets (Phase 4 — spec O1, R1, O3)
# ---------------------------------------------------------------------------

class OrganizationViewSet(viewsets.ModelViewSet):
    """CRUD for multi-tenant organizations — admin-only (spec O1).

    List/retrieve requires ``core:read``; create/update/destroy requires
    ``core:admin`` in the user's membership role permissions.
    """

    queryset = Organization.objects.all().order_by('name')
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('core', 'read')]
        return [permissions.IsAuthenticated(), OrgRolePermission('core', 'admin')]


class BranchViewSet(viewsets.ModelViewSet):
    """CRUD for physical branches.

    Requires ``core:read`` for list/retrieve, ``core:write`` for create/
    update, and ``core:admin`` for destroy.
    """

    queryset = Branch.objects.all().order_by('organization', 'name')
    serializer_class = BranchSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return branches scoped to the request org via OrgAwareManager."""
        return Branch.objects.all().order_by('name')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('core', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('core', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('core', 'write')]

    def perform_create(self, serializer):
        """Assign the request org to the new branch."""
        serializer.save(organization=self.request.organization)


class RoleViewSet(viewsets.ModelViewSet):
    """CRUD for per-org custom roles — admin-only (spec R1).

    List/retrieve requires ``core:read``; create/update/destroy requires
    ``core:admin``.
    """

    queryset = Role.objects.all().order_by('organization', 'name')
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return roles scoped to the request org via OrgAwareManager."""
        return Role.objects.all().order_by('name')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('core', 'read')]
        return [permissions.IsAuthenticated(), OrgRolePermission('core', 'admin')]

    def perform_create(self, serializer):
        """Assign the request org to the new role."""
        serializer.save(organization=self.request.organization)


class OrganizationMembershipViewSet(viewsets.ModelViewSet):
    """Manage user memberships in organizations (spec O3).

    - List/retrieve: members see only their own memberships (admins see all).
      All queries scoped to the request org via OrgAwareManager.
    - Create/update/destroy: requires ``core:write``.
    """

    queryset = (
        OrganizationMembership.objects
        .select_related('user', 'organization', 'role')
        .order_by('organization', 'user')
    )
    serializer_class = OrganizationMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Scope by request org (via OrgAwareManager) and optionally by user."""
        qs = (
            OrganizationMembership.objects
            .select_related('user', 'organization', 'role')
            .order_by('organization', 'user')
        )
        if self.action in ('list', 'retrieve') and not self.request.user.is_superuser:
            qs = qs.filter(user=self.request.user)
        return qs

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), OrgRolePermission('core', 'write')]

    def perform_create(self, serializer):
        """Assign the request org to the new membership."""
        serializer.save(organization=self.request.organization)
