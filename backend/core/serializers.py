import re

from django.core.validators import ValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import (
    Branch,
    CustomField,
    CustomFieldValue,
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

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        required=False,
        help_text='User password (write-only).',
    )

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'password',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'email': {'required': True},
        }

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])
        return user


# ---------------------------------------------------------------------------
# Multi-org serializers (spec O1, R1, R2)
# ---------------------------------------------------------------------------

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

    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    role_name = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationMembership
        fields = [
            'id', 'user', 'organization', 'role',
            'user_name', 'user_email', 'role_name',
            'is_default', 'is_active', 'is_owner',
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

    def get_user_name(self, obj):
        return obj.user.full_name if obj.user else None

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None

    def get_role_name(self, obj):
        return obj.role.name if obj.role else None


# ---------------------------------------------------------------------------
# RegisterSerializer — self-service signup (spec R1-R9)
# ---------------------------------------------------------------------------


class RegisterSerializer(serializers.Serializer):
    """Validates and creates a new user + organization in one atomic step.

    Fields:
        email       — RFC 5322, unique
        password    — ≥8 chars, ≥1 letter, ≥1 digit
        full_name   — max 255
        org_name    — max 255, unique
        org_tax_id  — optional, unique if provided

    The actual creation happens in RegisterView (transaction.atomic),
    not here — this serializer only validates input.
    """

    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
    )
    full_name = serializers.CharField(required=True, max_length=255)
    org_name = serializers.CharField(required=True, max_length=255)
    org_tax_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
    )

    def validate_password(self, value):
        """Password must have ≥1 letter and ≥1 digit (spec R5)."""
        if not re.search(r'[A-Za-z]', value):
            raise serializers.ValidationError(
                'Password must contain at least one letter and one digit.',
            )
        if not re.search(r'\d', value):
            raise serializers.ValidationError(
                'Password must contain at least one letter and one digit.',
            )
        return value

    def validate(self, data):
        """Cross-field uniqueness checks (spec R2/R3).

        Uses ``code='conflict'`` on ValidationError so the view can
        detect 409 vs 400 based on error codes.
        """
        email = data.get('email')
        org_name = data.get('org_name')
        org_tax_id = data.get('org_tax_id')

        if email and User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                {'email': 'A user with this email already exists.'},
                code='conflict',
            )

        if org_name and Organization.objects.filter(name=org_name).exists():
            raise serializers.ValidationError(
                {'org_name': 'An organization with this name already exists.'},
                code='conflict',
            )

        if org_tax_id and Organization.objects.filter(tax_id=org_tax_id).exists():
            raise serializers.ValidationError(
                {'org_tax_id': 'An organization with this tax ID already exists.'},
                code='conflict',
            )

        return data


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
        fields = ['id', 'organization', 'role', 'is_default', 'is_owner']


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


# ---------------------------------------------------------------------------
# CustomFieldSerializer — CRUD for field definitions
# ---------------------------------------------------------------------------


class CustomFieldSerializer(serializers.ModelSerializer):
    """CRUD for per-org custom field definitions.

    The ``organization`` field is read-only — it is assigned from
    ``request.organization`` in the view's ``perform_create``.
    """

    class Meta:
        model = CustomField
        fields = [
            'id', 'organization', 'model_name', 'name', 'field_type',
            'required', 'options', 'order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'organization']

    def validate(self, data):
        """Cross-field validation: select requires non-empty options,
        duplicate name per org+model rejected on create."""
        field_type = data.get('field_type')
        options = data.get('options')

        if field_type == 'select':
            if not options or not isinstance(options, list) or len(options) == 0:
                raise serializers.ValidationError(
                    {'options': 'Select fields require a non-empty list of options.'}
                )
        elif options:
            raise serializers.ValidationError(
                {'options': 'Options are only valid for select fields.'}
            )

        # Duplicate name check (only on create — update is handled by
        # the unique_together constraint at DB level).
        if self.instance is None:
            request = self.context.get('request')
            org = request.organization if request else None
            model_name = data.get('model_name')
            name = data.get('name')
            if org and model_name and name:
                if CustomField.objects.filter(
                    organization=org,
                    model_name=model_name,
                    name=name,
                ).exists():
                    raise serializers.ValidationError(
                        {'name': 'A field with this name already exists for this model.'}
                    )

        return data


# ---------------------------------------------------------------------------
# CustomFieldsMixin — injects custom_fields into entity serializers
# ---------------------------------------------------------------------------


class CustomFieldsMixin:
    """Mixin that adds writable ``custom_fields`` dict to any entity serializer.

    Usage::

        class ProductSerializer(CustomFieldsMixin, ModelSerializer):
            MODEL_NAME = 'product'

    The mixin:

    - Accepts ``custom_fields: {name: raw_value}`` on create/update.
    - Validates types, required flags, and select membership.
    - Persists values as ``CustomFieldValue`` rows.
    - Injectes the current values into the response via ``to_representation``.
    """

    MODEL_NAME = None          # set by each concrete serializer
    CUSTOM_FIELDS_KEY = 'custom_fields'

    def get_fields(self):
        """Inject custom_fields as a writable dict field so DRF does not
        strip it during deserialization."""
        fields = super().get_fields()
        if self.CUSTOM_FIELDS_KEY not in fields:
            fields[self.CUSTOM_FIELDS_KEY] = serializers.DictField(
                required=False, write_only=True,
            )
        return fields

    def _get_organization(self):
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            return request.organization
        return None

    def _get_field_definitions(self):
        org = self._get_organization()
        if org is None:
            return {}
        qs = CustomField.objects.filter(
            organization=org,
            model_name=self.MODEL_NAME,
        ).order_by('order', 'name')
        return {f.name: f for f in qs}

    # ------------------------------------------------------------------
    # Representation — inject current values into response
    # ------------------------------------------------------------------

    def to_representation(self, instance):
        data = super().to_representation(instance)
        org = self._get_organization()
        if org is None or self.MODEL_NAME is None:
            data[self.CUSTOM_FIELDS_KEY] = {}
            return data

        definitions = self._get_field_definitions()
        if not definitions:
            data[self.CUSTOM_FIELDS_KEY] = {}
            return data

        field_ids = [f.id for f in definitions.values()]
        values = CustomFieldValue.objects.filter(
            organization=org,
            entity_type=self.MODEL_NAME,
            entity_id=instance.id,
            field_id__in=field_ids,
        ).select_related('field')

        value_map = {v.field.name: v.value for v in values}
        # Type-cast values based on field_type
        casted = {}
        for name, field in definitions.items():
            raw = value_map.get(name, '')
            casted[name] = self._cast_value(raw, field)
        data[self.CUSTOM_FIELDS_KEY] = casted
        return data

    # ------------------------------------------------------------------
    # Validation — type-check, required check, store cleansed data
    # ------------------------------------------------------------------

    def validate(self, data):
        custom_fields = data.pop(self.CUSTOM_FIELDS_KEY, None)
        data = super().validate(data)
        if custom_fields is None or not isinstance(custom_fields, dict):
            self._custom_fields_data = {}
            return data

        definitions = self._get_field_definitions()
        self._custom_fields_data = {}

        for name, raw_value in custom_fields.items():
            field_def = definitions.get(name)
            if field_def is None:
                # Unknown field name — silently drop per spec
                continue
            self._custom_fields_data[name] = self._validate_and_cast(
                raw_value, field_def,
            )

        # Required-field enforcement for non-empty payloads on create/update
        instance = self.instance
        for name, field_def in definitions.items():
            if field_def.required:
                value = self._custom_fields_data.get(name)
                if value is None or (isinstance(value, str) and value.strip() == ''):
                    raise serializers.ValidationError({
                        self.CUSTOM_FIELDS_KEY: {
                            name: 'This field is required.',
                        },
                    })

        return data

    def _validate_and_cast(self, raw_value, field_def):
        """Validate and type-cast a single value against its field definition."""
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ''):
            if field_def.required:
                raise serializers.ValidationError({
                    self.CUSTOM_FIELDS_KEY: {
                        field_def.name: 'This field is required.',
                    },
                })
            return ''

        if field_def.field_type == 'number':
            try:
                from decimal import Decimal, InvalidOperation
                val = Decimal(str(raw_value))
                return str(val)
            except (ValueError, InvalidOperation):
                raise serializers.ValidationError({
                    self.CUSTOM_FIELDS_KEY: {
                        field_def.name: 'Enter a valid number.',
                    },
                })

        if field_def.field_type == 'date':
            import datetime
            if isinstance(raw_value, str):
                for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                    try:
                        parsed = datetime.datetime.strptime(raw_value, fmt)
                        return parsed.strftime('%Y-%m-%d')
                    except ValueError:
                        continue
                raise serializers.ValidationError({
                    self.CUSTOM_FIELDS_KEY: {
                        field_def.name: 'Enter a valid date (YYYY-MM-DD).',
                    },
                })
            return str(raw_value)

        if field_def.field_type == 'select':
            str_val = str(raw_value)
            valid_options = field_def.options or []
            if str_val not in valid_options:
                raise serializers.ValidationError({
                    self.CUSTOM_FIELDS_KEY: {
                        field_def.name: f'Must be one of: {", ".join(valid_options)}.',
                    },
                })
            return str_val

        # text — store as-is
        return str(raw_value)

    def _cast_value(self, raw, field_def):
        """Cast a stored text value back to its native type for the API response."""
        if raw is None or raw == '':
            return '' if field_def.required else None

        if field_def.field_type == 'number':
            from decimal import Decimal, ROUND_HALF_UP
            try:
                d = Decimal(raw)
                return str(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            except Exception:
                return raw

        if field_def.field_type == 'date':
            return raw  # already stored as ISO date

        return raw

    # ------------------------------------------------------------------
    # Persistence — create / update CustomFieldValues after entity save
    # ------------------------------------------------------------------

    def create(self, validated_data):
        custom_fields_data = getattr(self, '_custom_fields_data', {})
        instance = super().create(validated_data)
        if custom_fields_data:
            self._save_custom_field_values(instance, custom_fields_data)
        return instance

    def update(self, instance, validated_data):
        custom_fields_data = getattr(self, '_custom_fields_data', {})
        instance = super().update(instance, validated_data)
        if custom_fields_data:
            self._save_custom_field_values(instance, custom_fields_data)
        return instance

    def _save_custom_field_values(self, instance, custom_fields_data):
        """Persist custom field values for the given entity instance."""
        org = self._get_organization()
        if org is None or self.MODEL_NAME is None:
            return

        definitions = self._get_field_definitions()
        for name, value in custom_fields_data.items():
            field_def = definitions.get(name)
            if field_def is None:
                continue

            CustomFieldValue.objects.update_or_create(
                organization=org,
                entity_type=self.MODEL_NAME,
                entity_id=instance.id,
                field=field_def,
                defaults={'value': value},
            )


# ---------------------------------------------------------------------------
# OrganizationSerializer — placed after CustomFieldsMixin to resolve import
# order (mixin must be defined before use).
# ---------------------------------------------------------------------------

class OrganizationSerializer(CustomFieldsMixin, serializers.ModelSerializer):
    """CRUD for multi-tenant organizations.

    tax_id uniqueness is enforced at the model level (unique=True).
    """

    MODEL_NAME = 'organization'

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'tax_id', 'is_active', 'settings',
            'legal_name', 'tax_regime', 'fiscal_address',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
