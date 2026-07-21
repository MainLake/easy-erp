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
            'id', 'email', 'full_name', 'role',
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
    """CRUD for physical branches belonging to an organization."""

    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'address', 'organization', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RoleSerializer(serializers.ModelSerializer):
    """CRUD for per-org custom roles with JSON permission maps.

    Permissions are validated by ``validate_permissions_schema`` both at
    the field level (model validator) and on serializer ``validate`` to
    catch invalid modules/actions before hitting the DB (spec R1, R2).
    """

    class Meta:
        model = Role
        fields = [
            'id', 'name', 'organization', 'permissions',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_permissions(self, value):
        validate_permissions_schema(value)
        return value


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    """Links a user to an organization with a role.

    Enforces (user, organization) uniqueness via DRF validator plus
    model-level unique_together (spec O3).
    """

    class Meta:
        model = OrganizationMembership
        fields = [
            'id', 'user', 'organization', 'role',
            'is_default', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        validators = [
            UniqueTogetherValidator(
                queryset=OrganizationMembership.objects.all(),
                fields=['user', 'organization'],
                message='This user already has a membership in this organization.',
            ),
        ]
