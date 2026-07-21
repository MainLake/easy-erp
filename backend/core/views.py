from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Branch, Organization, OrganizationMembership, Role, User
from .serializers import (
    BranchSerializer,
    MeSerializer,
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

    def get_serializer_class(self):
        """Use MeSerializer for /users/me/ so the response includes memberships."""
        if self.action == 'me':
            return MeSerializer
        return UserSerializer

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


class SwitchOrgView(APIView):
    """Switch the user's active organization and return fresh JWT tokens.

    POST /api/v1/auth/switch-org/
    Body: {"organization_id": "<UUID>"}

    Validates the user is a member of the requested organization, then
    issues a new access+refresh token pair with ``active_organization_id``
    set to the target org (spec A5).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        organization_id = request.data.get('organization_id')

        if not organization_id:
            return Response(
                {
                    'data': None,
                    'errors': [{
                        'code': 'bad_request',
                        'message': 'organization_id es requerido',
                    }],
                    'meta': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not OrganizationMembership.all_objects.filter(
            user=request.user, organization_id=organization_id,
        ).exists():
            return Response(
                {
                    'data': None,
                    'errors': [{
                        'code': 'not_member',
                        'message': 'No sos miembro de esta organización',
                    }],
                    'meta': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(request.user)
        refresh['active_organization_id'] = str(organization_id)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })
