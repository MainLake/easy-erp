from django.core.validators import ValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import (
    Branch,
    Organization,
    OrganizationMembership,
    Role,
    User,
    validate_permissions_schema,
)


class UserSerializer(serializers.ModelSerializer):
    """Serialize User model for API responses.

    Password is write-only and never exposed in responses.
    """

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'email': {'required': True},
        }


# ---------------------------------------------------------------------------
# Multi-org serializers (spec O1, R1, R2)
# ---------------------------------------------------------------------------

class OrganizationSerializer(serializers.ModelSerializer):
    """CRUD for multi-tenant organizations.

    tax_id uniqueness is enforced at the model level (unique=True).
    """

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'tax_id', 'is_active', 'settings',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BranchSerializer(serializers.ModelSerializer):
    """CRUD for physical branches belonging to an organization.

    The ``organization`` field is read-only — it is assigned from
    ``request.organization`` in the view's ``perform_create``.
    """

    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'address', 'organization', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'organization']


class RoleSerializer(serializers.ModelSerializer):
    """CRUD for per-org custom roles with JSON permission maps.

    Permissions are validated by ``validate_permissions_schema`` both at
    the field level (model validator) and on serializer ``validate`` to
    catch invalid modules/actions before hitting the DB (spec R1, R2).

    The ``organization`` field is read-only — it is assigned from
    ``request.organization`` in the view's ``perform_create``.
    """

    class Meta:
        model = Role
        fields = [
            'id', 'name', 'organization', 'permissions',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'organization']

    def validate_permissions(self, value):
        validate_permissions_schema(value)
        return value


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    """Links a user to an organization with a role.

    Enforces (user, organization) uniqueness via DRF validator plus
    model-level unique_together (spec O3).

    The ``organization`` field is read-only — it is assigned from
    ``request.organization`` in the view's ``perform_create``.
    """

    class Meta:
        model = OrganizationMembership
        fields = [
            'id', 'user', 'organization', 'role',
            'is_default', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'organization']
        validators = [
            UniqueTogetherValidator(
                queryset=OrganizationMembership.objects.all(),
                fields=['user', 'organization'],
                message='This user already has a membership in this organization.',
            ),
        ]


# ---------------------------------------------------------------------------
# MeSerializer — self-serve user detail with memberships (spec A4, A5)
# ---------------------------------------------------------------------------

class RoleSummarySerializer(serializers.ModelSerializer):
    """Lightweight role info for the MeSerializer membership nesting."""

    class Meta:
        model = Role
        fields = ['id', 'name', 'permissions']


class OrganizationSummarySerializer(serializers.ModelSerializer):
    """Lightweight org info for the MeSerializer membership nesting."""

    class Meta:
        model = Organization
        fields = ['id', 'name', 'tax_id']


class OrganizationMembershipNestedSerializer(serializers.ModelSerializer):
    """Nested membership serializer for MeSerializer.

    Includes the related organization and role as nested sub-objects.
    """

    organization = OrganizationSummarySerializer(read_only=True)
    role = RoleSummarySerializer(read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ['id', 'organization', 'role', 'is_default']


class MeSerializer(UserSerializer):
    """Extends UserSerializer with the user's organization memberships.

    Used exclusively by the ``/users/me/`` endpoint so that the
    frontend can discover the user's orgs, roles, and default
    membership without hitting a separate endpoint (spec A4, A5).

    Uses ``SerializerMethodField`` to bypass OrgAwareManager filtering
    on the reverse relation.
    """

    memberships = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['memberships']

    def get_memberships(self, user):
        """Return all memberships for this user, scoped only by user (not org)."""
        qs = (
            OrganizationMembership.all_objects
            .filter(user=user)
            .select_related('organization', 'role')
            .order_by('organization__name')
        )
        return OrganizationMembershipNestedSerializer(qs, many=True).data
