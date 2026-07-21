from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from django.db import transaction

from .models import Branch, CustomField, Organization, OrganizationMembership, Role, User
from .serializers import (
    BranchSerializer,
    CustomFieldSerializer,
    MeSerializer,
    OrganizationMembershipSerializer,
    OrganizationSerializer,
    RegisterSerializer,
    RoleSerializer,
    UserSerializer,
)
from .permissions import IsOrgOwner, OrgRolePermission


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_error_response(errors):
    """Convert RegisterSerializer errors to the API envelope.

    If any error has code='conflict', the HTTP status is 409;
    otherwise 400 (spec R2/R3).
    """
    is_conflict = False
    formatted = []

    for field, messages in errors.items():
        if isinstance(messages, list):
            for msg in messages:
                if hasattr(msg, 'code') and msg.code == 'conflict':
                    is_conflict = True
                else:
                    code = getattr(msg, 'code', 'bad_request')
                    if code == 'conflict':
                        is_conflict = True
                formatted.append({
                    'code': getattr(msg, 'code', 'bad_request'),
                    'field': field,
                    'message': str(msg),
                })
        else:
            code = getattr(messages, 'code', 'bad_request')
            if code == 'conflict':
                is_conflict = True
            formatted.append({
                'code': code,
                'field': field,
                'message': str(messages),
            })

    # Also check the errors dict for DRF-level error codes
    if hasattr(errors, 'get_codes'):
        codes = errors.get_codes()
        for field_codes in codes.values():
            if isinstance(field_codes, list):
                for c in field_codes:
                    if c == 'conflict':
                        is_conflict = True
                        break
            elif field_codes == 'conflict':
                is_conflict = True
                break

    http_status = status.HTTP_409_CONFLICT if is_conflict else status.HTTP_400_BAD_REQUEST

    return Response(
        {
            'data': None,
            'errors': formatted,
            'meta': {},
        },
        status=http_status,
    )


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

    Update/destroy additionally requires org ownership (IsOrgOwner).
    """

    queryset = Organization.objects.all().order_by('name')
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('core', 'read')]
        if self.action in ('update', 'partial_update', 'destroy'):
            return [
                permissions.IsAuthenticated(),
                OrgRolePermission('core', 'admin'),
                IsOrgOwner(),
            ]
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
        """Scope by request org (via OrgAwareManager) and optionally by user.

        Owners see all members in their org. Regular members only see themselves.
        """
        qs = (
            OrganizationMembership.objects
            .select_related('user', 'organization', 'role')
            .order_by('organization', 'user')
        )
        if self.action in ('list', 'retrieve') and not self.request.user.is_superuser:
            # Check if user is an owner of the current org
            is_owner = OrganizationMembership.objects.filter(
                user=self.request.user,
                organization=self.request.organization,
                is_owner=True,
            ).exists()
            if not is_owner:
                qs = qs.filter(user=self.request.user)
        return qs

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), OrgRolePermission('core', 'write')]

    def perform_create(self, serializer):
        """Assign the request org to the new membership."""
        serializer.save(organization=self.request.organization)


class CustomFieldViewSet(viewsets.ModelViewSet):
    """CRUD for per-org custom field definitions — owner-only mutations.

    Org owners can create, update, and delete field definitions for their
    organization.  All org members can list and retrieve definitions for
    the current model type.
    """

    queryset = CustomField.objects.all().order_by('order', 'name')
    serializer_class = CustomFieldSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return field definitions scoped to the request org via OrgAwareManager."""
        return CustomField.objects.all().order_by('order', 'name')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOrgOwner()]

    def perform_create(self, serializer):
        """Assign the request org to the new field definition."""
        serializer.save(organization=self.request.organization)


class RegisterView(APIView):
    """Self-service registration — creates User + Organization + Admin Role
    + Owner Membership atomically and returns JWT tokens (spec R1-R9).

    POST /api/v1/auth/register/
    Body: {email, password, full_name, org_name, [org_tax_id]}

    No authentication required.
    """

    permission_classes = []
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return _register_error_response(serializer.errors)

        data = serializer.validated_data

        try:
            with transaction.atomic():
                # 1 — Create User
                user = User.objects.create_user(
                    email=data['email'],
                    password=data['password'],
                    full_name=data['full_name'],
                )

                # 2 — Create Organization
                org = Organization.objects.create(
                    name=data['org_name'],
                    tax_id=data.get('org_tax_id') or data['org_name'],
                )

                # 3 — Create Admin Role with wildcard permissions (spec R8)
                role = Role.objects.create(
                    name='Admin',
                    organization=org,
                    permissions={'*': ['admin']},
                )

                # 4 — Create Owner Membership (spec O1)
                OrganizationMembership.objects.create(
                    user=user,
                    organization=org,
                    role=role,
                    is_owner=True,
                    is_default=True,
                )

        except Exception:
            # Any unexpected failure → 500
            return Response(
                {
                    'data': None,
                    'errors': [{
                        'code': 'server_error',
                        'message': 'Registration failed. Please try again.',
                    }],
                    'meta': {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Issue JWT tokens with active organization claim (spec R7)
        refresh = RefreshToken.for_user(user)
        refresh['active_organization_id'] = str(org.id)

        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


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
