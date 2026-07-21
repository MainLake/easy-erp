"""
Unit tests for CustomField and CustomFieldValue models, ViewSet CRUD,
CustomFieldsMixin validation, and type casting.

Spec coverage:
  - Field Definition CRUD (owner-only mutation, duplicate rejection)
  - Field Type and Option Constraints (select requires options)
  - Value Storage and Retrieval (custom_fields dict in serializers)
  - Value Validation (type casting, required enforcement, unknown-field drop)
  - Orphan Value Cleanup (CASCADE on field FK)
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from core.models import (
    CustomField,
    CustomFieldValue,
    Organization,
    OrganizationMembership,
    Role,
)
from core.serializers import CustomFieldsMixin, CustomFieldSerializer
from rest_framework import serializers
from rest_framework.request import Request

User = get_user_model()


# =============================================================================
# CustomField model unit tests
# =============================================================================

class CustomFieldModelTests(TestCase):
    """CustomField model: create, duplicate rejection, select-options
    validation, org scoping, ordering."""

    def setUp(self):
        self.org = Organization.objects.create(name='CF Org', tax_id='CF-001')
        self.org2 = Organization.objects.create(name='CF Org 2', tax_id='CF-002')

    # --- Creation ---

    def test_create_text_field(self):
        """GIVEN valid data / WHEN creating a text CustomField / THEN persisted."""
        cf = CustomField.objects.create(
            organization=self.org,
            model_name='product',
            name='SKU',
            field_type='text',
            required=False,
            order=1,
        )
        self.assertEqual(cf.name, 'SKU')
        self.assertEqual(cf.field_type, 'text')
        self.assertEqual(cf.model_name, 'product')
        self.assertFalse(cf.required)
        self.assertEqual(cf.order, 1)
        self.assertIsNotNone(cf.id)

    def test_create_select_field_with_options(self):
        """GIVEN select field with options / WHEN created / THEN options stored."""
        cf = CustomField.objects.create(
            organization=self.org,
            model_name='product',
            name='Size',
            field_type='select',
            required=False,
            options=['S', 'M', 'L'],
            order=2,
        )
        self.assertEqual(cf.options, ['S', 'M', 'L'])

    def test_create_number_field(self):
        """GIVEN number field / WHEN created / THEN persisted."""
        cf = CustomField.objects.create(
            organization=self.org,
            model_name='customer',
            name='CreditLimit',
            field_type='number',
            required=False,
            order=0,
        )
        self.assertEqual(cf.field_type, 'number')

    def test_create_date_field(self):
        """GIVEN date field / WHEN created / THEN persisted."""
        cf = CustomField.objects.create(
            organization=self.org,
            model_name='supplier',
            name='ContractDate',
            field_type='date',
            required=False,
            order=3,
        )
        self.assertEqual(cf.field_type, 'date')

    # --- Duplicate rejection ---

    def test_duplicate_name_same_org_model_rejected(self):
        """GIVEN field 'RFC' for supplier in org / WHEN creating another
        'RFC' for supplier in same org / THEN IntegrityError."""
        CustomField.objects.create(
            organization=self.org,
            model_name='supplier',
            name='RFC',
            field_type='text',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CustomField.objects.create(
                    organization=self.org,
                    model_name='supplier',
                    name='RFC',
                    field_type='text',
                )

    def test_same_name_different_org_allowed(self):
        """GIVEN field 'RFC' in org1 / WHEN creating 'RFC' in org2 / THEN allowed."""
        CustomField.objects.create(
            organization=self.org,
            model_name='supplier',
            name='RFC',
            field_type='text',
        )
        cf = CustomField.objects.create(
            organization=self.org2,
            model_name='supplier',
            name='RFC',
            field_type='text',
        )
        self.assertEqual(cf.organization, self.org2)

    def test_same_name_different_model_allowed(self):
        """GIVEN field 'RFC' for Supplier / WHEN creating 'RFC' for Customer
        in same org / THEN allowed (different model_name)."""
        CustomField.objects.create(
            organization=self.org,
            model_name='supplier',
            name='RFC',
            field_type='text',
        )
        cf = CustomField.objects.create(
            organization=self.org,
            model_name='customer',
            name='RFC',
            field_type='text',
        )
        self.assertEqual(cf.model_name, 'customer')

    # --- Select options validation ---

    def test_select_without_options_clean_rejected(self):
        """GIVEN select field with no options / WHEN clean() / THEN ValidationError."""
        cf = CustomField(
            organization=self.org,
            model_name='product',
            name='Color',
            field_type='select',
            options=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            cf.clean()
        self.assertIn('options', str(ctx.exception))

    def test_select_with_empty_options_rejected(self):
        """GIVEN select field with empty options list / WHEN clean() / THEN ValidationError."""
        cf = CustomField(
            organization=self.org,
            model_name='product',
            name='Color',
            field_type='select',
            options=[],
        )
        with self.assertRaises(ValidationError) as ctx:
            cf.clean()
        self.assertIn('options', str(ctx.exception))

    def test_non_select_with_options_clean_rejected(self):
        """GIVEN text field with options set / WHEN clean() / THEN ValidationError."""
        cf = CustomField(
            organization=self.org,
            model_name='product',
            name='SKU',
            field_type='text',
            options=['A', 'B'],
        )
        with self.assertRaises(ValidationError) as ctx:
            cf.clean()
        self.assertIn('options', str(ctx.exception))

    def test_select_with_valid_options_clean_succeeds(self):
        """GIVEN select field with valid options / WHEN clean() / THEN no error."""
        cf = CustomField(
            organization=self.org,
            model_name='product',
            name='Size',
            field_type='select',
            options=['S', 'M'],
        )
        cf.clean()  # should not raise

    def test_number_field_no_options_clean_succeeds(self):
        """GIVEN number field with no options / WHEN clean() / THEN no error."""
        cf = CustomField(
            organization=self.org,
            model_name='product',
            name='Price',
            field_type='number',
            options=None,
        )
        cf.clean()

    # --- Ordering ---

    def test_fields_ordered_by_order_then_name(self):
        """GIVEN three fields with varying order / WHEN queried / THEN
        ordered by order asc, then name."""
        CustomField.objects.create(
            organization=self.org, model_name='product',
            name='C', field_type='text', order=2,
        )
        CustomField.objects.create(
            organization=self.org, model_name='product',
            name='A', field_type='text', order=1,
        )
        CustomField.objects.create(
            organization=self.org, model_name='product',
            name='B', field_type='text', order=1,
        )
        names = list(
            CustomField.objects
            .filter(organization=self.org, model_name='product')
            .values_list('name', flat=True)
        )
        self.assertEqual(names, ['A', 'B', 'C'])

    # --- String representation ---

    def test_str_includes_name_model_and_org(self):
        cf = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='SKU', field_type='text',
        )
        s = str(cf)
        self.assertIn('SKU', s)
        self.assertIn('Product', s)
        self.assertIn(self.org.name, s)


# =============================================================================
# CustomFieldValue model unit tests
# =============================================================================

class CustomFieldValueModelTests(TestCase):
    """CustomFieldValue: create, unique constraint, CASCADE on field delete."""

    def setUp(self):
        self.org = Organization.objects.create(name='CFV Org', tax_id='CFV-001')
        self.cf = CustomField.objects.create(
            organization=self.org,
            model_name='product',
            name='SKU',
            field_type='text',
            order=1,
        )
        self.cf2 = CustomField.objects.create(
            organization=self.org,
            model_name='product',
            name='Weight',
            field_type='number',
            order=2,
        )

    def test_create_value(self):
        """GIVEN a CustomField / WHEN creating a value / THEN persisted."""
        entity_id = '11111111-1111-1111-1111-111111111111'
        cfv = CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='product',
            entity_id=entity_id,
            field=self.cf,
            value='ABC-123',
        )
        self.assertEqual(cfv.value, 'ABC-123')
        self.assertEqual(cfv.field, self.cf)
        self.assertEqual(cfv.entity_type, 'product')

    def test_unique_per_entity_field(self):
        """GIVEN existing value for (entity, field) / WHEN creating
        duplicate / THEN IntegrityError."""
        entity_id = '22222222-2222-2222-2222-222222222222'
        CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='product',
            entity_id=entity_id,
            field=self.cf,
            value='val1',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CustomFieldValue.objects.create(
                    organization=self.org,
                    entity_type='product',
                    entity_id=entity_id,
                    field=self.cf,
                    value='val2',
                )

    def test_multiple_values_for_same_entity_different_fields(self):
        """GIVEN two different fields / WHEN creating values for the same
        entity / THEN both persisted."""
        entity_id = '33333333-3333-3333-3333-333333333333'
        v1 = CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='product',
            entity_id=entity_id,
            field=self.cf,
            value='ABC',
        )
        v2 = CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='product',
            entity_id=entity_id,
            field=self.cf2,
            value='12.5',
        )
        self.assertEqual(
            CustomFieldValue.objects.filter(entity_id=entity_id).count(),
            2,
        )

    def test_cascade_delete_field_removes_values(self):
        """GIVEN values attached to a field / WHEN field deleted /
        THEN values are cascade-deleted."""
        entity_id = '44444444-4444-4444-4444-444444444444'
        CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='product',
            entity_id=entity_id,
            field=self.cf,
            value='ABC',
        )
        self.assertEqual(CustomFieldValue.objects.count(), 1)
        self.cf.delete()
        self.assertEqual(CustomFieldValue.objects.count(), 0)

    def test_str_includes_field_name_and_value(self):
        cfv = CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='product',
            entity_id='55555555-5555-5555-5555-555555555555',
            field=self.cf,
            value='TEST-VALUE',
        )
        s = str(cfv)
        self.assertIn('SKU', s)
        self.assertIn('TEST-VALUE', s)

    def test_value_defaults_empty_string(self):
        """GIVEN value not provided / WHEN created / THEN defaults to ''."""
        cfv = CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='product',
            entity_id='66666666-6666-6666-6666-666666666666',
            field=self.cf,
        )
        self.assertEqual(cfv.value, '')


# =============================================================================
# ViewSet integration tests
# =============================================================================

class CustomFieldViewSetTests(TestCase):
    """CustomFieldViewSet: owner CRUD, non-owner 403, org scoping."""

    def setUp(self):
        from core.tests import OrgTestMixin
        self.client = APIClient()

        # Org with owner
        self.org = Organization.objects.create(name='CF API Org', tax_id='CFAPI-001')
        self.admin_role = Role.objects.create(
            name='Admin', organization=self.org,
            permissions={'core': ['admin']},
        )
        self.owner = User.objects.create_user(
            email='cf-owner@test.com', password='Pass1234', full_name='Owner',
        )
        OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, role=self.admin_role,
            is_owner=True, is_default=True,
        )

        # Non-owner member in same org
        self.member = User.objects.create_user(
            email='cf-member@test.com', password='Pass1234', full_name='Member',
        )
        member_role = Role.objects.create(
            name='Member', organization=self.org,
            permissions={'core': ['read']},
        )
        OrganizationMembership.objects.create(
            user=self.member, organization=self.org, role=member_role,
            is_owner=False, is_default=False,
        )

        # Org 2 — different org, for isolation tests
        self.org2 = Organization.objects.create(name='CF API Org 2', tax_id='CFAPI-002')
        self.role2 = Role.objects.create(
            name='Admin', organization=self.org2,
            permissions={'core': ['admin']},
        )
        self.owner2 = User.objects.create_user(
            email='cf-owner2@test.com', password='Pass1234', full_name='Owner2',
        )
        OrganizationMembership.objects.create(
            user=self.owner2, organization=self.org2, role=self.role2,
            is_owner=True, is_default=True,
        )

    def _login(self, email):
        # Clear any prior credentials to prevent stale JWT tokens from
        # leaking into the login request and setting a wrong thread-local
        # org that would trip OrgAwareManager on user.memberships.
        self.client.credentials()
        resp = self.client.post('/api/v1/auth/login/', {
            'email': email, 'password': 'Pass1234',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')


    # --- Create ---

    def test_owner_can_create_field(self):
        """GIVEN authenticated org owner / WHEN POST custom-fields / THEN 201."""
        self._login('cf-owner@test.com')
        response = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product',
            'name': 'SKU',
            'field_type': 'text',
            'required': False,
            'order': 1,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'SKU')
        self.assertEqual(response.data['model_name'], 'product')
        self.assertEqual(response.data['field_type'], 'text')

    def test_non_owner_cannot_create_field(self):
        """GIVEN non-owner org member / WHEN POST custom-fields / THEN 403."""
        self._login('cf-member@test.com')
        response = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product',
            'name': 'SKU',
            'field_type': 'text',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_select_field_with_options(self):
        """GIVEN owner / WHEN creating select field with options / THEN 201."""
        self._login('cf-owner@test.com')
        response = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product',
            'name': 'Size',
            'field_type': 'select',
            'options': ['S', 'M', 'L'],
            'order': 2,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['options'], ['S', 'M', 'L'])

    def test_create_select_without_options_rejected(self):
        """GIVEN owner / WHEN creating select without options / THEN 400."""
        self._login('cf-owner@test.com')
        response = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product',
            'name': 'Color',
            'field_type': 'select',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_name_rejected_at_api_level(self):
        """GIVEN existing field 'RFC' / WHEN creating duplicate / THEN 400."""
        self._login('cf-owner@test.com')
        self.client.post('/api/v1/custom-fields/', {
            'model_name': 'supplier', 'name': 'RFC', 'field_type': 'text',
        }, format='json')

        response = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'supplier', 'name': 'RFC', 'field_type': 'text',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', str(response.data))

    # --- List / Retrieve ---

    def test_list_returns_org_scoped_fields(self):
        """GIVEN fields in two orgs / WHEN owner1 lists / THEN only org1 fields."""
        self._login('cf-owner@test.com')
        create_resp = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product', 'name': 'SKU', 'field_type': 'text',
            'order': 1,
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED,
                         f'Create failed: {create_resp.data}')

        # Verify field exists in DB
        self.assertEqual(CustomField.objects.filter(name='SKU').count(), 1)

        # Owner2 creates field in org2
        self._login('cf-owner2@test.com')
        create_resp2 = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product', 'name': 'Material', 'field_type': 'text',
            'order': 1,
        }, format='json')
        self.assertEqual(create_resp2.status_code, status.HTTP_201_CREATED)

        # Verify both fields exist in DB (total count before org filtering)
        self.assertGreaterEqual(CustomField.objects.count(), 2)

        # Owner1 lists
        self._login('cf-owner@test.com')
        response = self.client.get('/api/v1/custom-fields/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()['data']
        self.assertEqual(len(results), 1,
                        f'Expected 1 field, got {len(results)}: {results}')
        self.assertEqual(results[0]['name'], 'SKU')

    def test_member_can_list_fields(self):
        """GIVEN non-owner member / WHEN GET custom-fields / THEN 200."""
        self._login('cf-owner@test.com')
        create_resp = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product', 'name': 'SKU', 'field_type': 'text',
            'order': 1,
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED,
                         f'Create failed: {create_resp.data}')

        self._login('cf-member@test.com')
        response = self.client.get('/api/v1/custom-fields/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()['data']
        self.assertEqual(len(results), 1,
                        f'Expected 1 field, got {len(results)}: {results}')

    # --- Update ---

    def test_owner_can_update_field(self):
        """GIVEN existing field / WHEN owner PATCHes / THEN 200."""
        self._login('cf-owner@test.com')
        create_resp = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product', 'name': 'SKU', 'field_type': 'text',
        }, format='json')
        field_id = create_resp.data['id']

        response = self.client.patch(
            f'/api/v1/custom-fields/{field_id}/',
            {'required': True, 'order': 5},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['required'])
        self.assertEqual(response.data['order'], 5)

    def test_non_owner_cannot_update_field(self):
        """GIVEN existing field / WHEN non-owner PATCHes / THEN 403."""
        self._login('cf-owner@test.com')
        create_resp = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product', 'name': 'SKU', 'field_type': 'text',
        }, format='json')
        field_id = create_resp.data['id']

        self._login('cf-member@test.com')
        response = self.client.patch(
            f'/api/v1/custom-fields/{field_id}/',
            {'name': 'Changed'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- Delete ---

    def test_owner_can_delete_field(self):
        """GIVEN existing field / WHEN owner DELETEs / THEN 204."""
        self._login('cf-owner@test.com')
        create_resp = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product', 'name': 'SKU', 'field_type': 'text',
        }, format='json')
        field_id = create_resp.data['id']

        response = self.client.delete(f'/api/v1/custom-fields/{field_id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            CustomField.objects.filter(id=field_id).exists()
        )

    def test_non_owner_cannot_delete_field(self):
        """GIVEN existing field / WHEN non-owner DELETEs / THEN 403."""
        self._login('cf-owner@test.com')
        create_resp = self.client.post('/api/v1/custom-fields/', {
            'model_name': 'product', 'name': 'SKU', 'field_type': 'text',
        }, format='json')
        field_id = create_resp.data['id']

        self._login('cf-member@test.com')
        response = self.client.delete(f'/api/v1/custom-fields/{field_id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =============================================================================
# CustomFieldsMixin unit tests (type casting, validation)
# =============================================================================

class CustomFieldsMixinValidationTests(TestCase):
    """CustomFieldsMixin: type casting, required enforcement, unknown-field drop."""

    def setUp(self):
        self.org = Organization.objects.create(name='Mixin Org', tax_id='MX-001')
        self.factory = APIRequestFactory()

        # Create field definitions
        self.cf_text = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Notes', field_type='text', required=False, order=1,
        )
        self.cf_number = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Weight', field_type='number', required=False, order=2,
        )
        self.cf_required = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='SKU', field_type='text', required=True, order=3,
        )
        self.cf_select = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Size', field_type='select',
            options=['S', 'M', 'L'], required=False, order=4,
        )
        self.cf_date = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Expiry', field_type='date', required=False, order=5,
        )

        # A serializer instance for direct method tests
        class DummySerializer(CustomFieldsMixin, serializers.Serializer):
            MODEL_NAME = 'product'
            name = serializers.CharField()
            def to_representation(self, instance):
                return {}
        self.serializer = DummySerializer()

    def _make_serializer(self, data=None):
        """Create a test serializer with the mixin applied.

        Uses a DRF Request wrapper so the serializer context gets a
        proper request object with ``.organization`` set.
        """

        class TestModel:
            id = '11111111-1111-1111-1111-111111111111'

        class TestSerializer(CustomFieldsMixin, serializers.Serializer):
            MODEL_NAME = 'product'
            name = serializers.CharField()

            def create(self, validated_data):
                return TestModel()

            def update(self, instance, validated_data):
                return instance

            def to_representation(self, instance):
                return {'name': 'Test', 'id': str(instance.id)}

        django_request = self.factory.post('/fake/', data or {}, format='json')
        drf_request = Request(django_request)
        drf_request.organization = self.org
        return TestSerializer(data=data, context={'request': drf_request})

    # --- Type casting (via validate_and_cast directly to isolate from required checks) ---

    def test_number_field_accepts_integer(self):
        """GIVEN number field / WHEN integer value submitted / THEN cast to str."""
        result = self.serializer._validate_and_cast(100, self.cf_number)
        self.assertEqual(result, '100')

    def test_number_field_accepts_decimal_string(self):
        """GIVEN number field / WHEN decimal string submitted / THEN cast."""
        result = self.serializer._validate_and_cast('12.50', self.cf_number)
        self.assertEqual(result, '12.50')

    def test_number_field_rejects_non_numeric(self):
        """GIVEN number field / WHEN 'large' submitted / THEN ValidationError."""
        from rest_framework import serializers as drf_serializers
        with self.assertRaises(drf_serializers.ValidationError):
            self.serializer._validate_and_cast('large', self.cf_number)

    def test_date_field_accepts_iso_date(self):
        """GIVEN date field / WHEN ISO date string / THEN normalized."""
        result = self.serializer._validate_and_cast('2025-12-31', self.cf_date)
        self.assertEqual(result, '2025-12-31')

    def test_date_field_accepts_slash_format(self):
        """GIVEN date field / WHEN DD/MM/YYYY / THEN normalized to ISO."""
        result = self.serializer._validate_and_cast('31/12/2025', self.cf_date)
        self.assertEqual(result, '2025-12-31')

    def test_date_field_rejects_invalid_date(self):
        """GIVEN date field / WHEN 'next week' / THEN ValidationError."""
        from rest_framework import serializers as drf_serializers
        with self.assertRaises(drf_serializers.ValidationError):
            self.serializer._validate_and_cast('next week', self.cf_date)

    def test_text_field_accepts_any_string(self):
        """GIVEN text field / WHEN any string / THEN stored as-is."""
        result = self.serializer._validate_and_cast('Some notes here', self.cf_text)
        self.assertEqual(result, 'Some notes here')

    def test_select_field_accepts_valid_option(self):
        """GIVEN select field with options ['S','M','L'] / WHEN 'M' / THEN accepted."""
        result = self.serializer._validate_and_cast('M', self.cf_select)
        self.assertEqual(result, 'M')

    def test_select_field_rejects_invalid_option(self):
        """GIVEN select field / WHEN 'XL' not in options / THEN rejected."""
        from rest_framework import serializers as drf_serializers
        with self.assertRaises(drf_serializers.ValidationError):
            self.serializer._validate_and_cast('XL', self.cf_select)

    # --- Required field enforcement (full validate flow) ---

    def test_required_field_provided_passes(self):
        """GIVEN required field 'SKU' / WHEN provided / THEN valid."""
        serializer = self._make_serializer({
            'name': 'Test',
            'custom_fields': {'SKU': 'ABC-123'},
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer._custom_fields_data['SKU'], 'ABC-123')

    def test_required_field_missing_blocks_validation(self):
        """GIVEN required field 'SKU' / WHEN omitted / THEN ValidationError."""
        serializer = self._make_serializer({
            'name': 'Test',
            'custom_fields': {'Notes': 'hello'},
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('custom_fields', serializer.errors)

    def test_required_field_empty_string_blocks(self):
        """GIVEN required field 'SKU' / WHEN empty string / THEN ValidationError."""
        serializer = self._make_serializer({
            'name': 'Test',
            'custom_fields': {'SKU': ''},
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('custom_fields', serializer.errors)

    # --- Unknown field drop ---

    def test_unknown_field_name_silently_dropped(self):
        """GIVEN no CustomField named 'Color' / WHEN submitted alongside
        a valid field / THEN unknown name is dropped, valid field preserved."""
        serializer = self._make_serializer({
            'name': 'Test',
            'custom_fields': {'Color': 'Red', 'Notes': 'ok', 'SKU': 'REQ-001'},
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn('Color', serializer._custom_fields_data)
        self.assertIn('Notes', serializer._custom_fields_data)
        self.assertIn('SKU', serializer._custom_fields_data)

    # --- No custom_fields key ---

    def test_no_custom_fields_key_succeeds(self):
        """GIVEN no custom_fields key / WHEN validating / THEN valid."""
        serializer = self._make_serializer({'name': 'Test'})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_empty_custom_fields_dict_validates_required(self):
        """GIVEN empty custom_fields dict / WHEN validated / THEN required
        check applies (SKU is required and missing)."""
        serializer = self._make_serializer({
            'name': 'Test',
            'custom_fields': {},
        })
        # SKU is required — should block
        self.assertFalse(serializer.is_valid(), serializer.errors)
        self.assertIn('custom_fields', serializer.errors)

    # --- Numeric type casting edge cases ---

    def test_number_field_accepts_negative_number(self):
        """GIVEN number field / WHEN negative value / THEN cast correctly."""
        result = self.serializer._validate_and_cast('-5.5', self.cf_number)
        self.assertEqual(result, '-5.5')

    def test_number_field_accepts_zero(self):
        """GIVEN number field / WHEN '0' / THEN cast correctly."""
        result = self.serializer._validate_and_cast('0', self.cf_number)
        self.assertEqual(result, '0')


# =============================================================================
# _cast_value helper tests
# =============================================================================

class CustomFieldsMixinCastTests(TestCase):
    """Test _cast_value method for all field types."""

    def setUp(self):
        self.org = Organization.objects.create(name='Cast Org', tax_id='CAST-001')
        self.cf_text = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Notes', field_type='text', required=False, order=1,
        )
        self.cf_number = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Weight', field_type='number', required=False, order=2,
        )
        self.cf_date = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Expiry', field_type='date', required=False, order=3,
        )
        self.cf_select = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Size', field_type='select',
            options=['S', 'M', 'L'], required=False, order=4,
        )
        self.cf_req = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='SKU', field_type='text', required=True, order=5,
        )

        # We need a dummy instance with a serializer to call _cast_value.
        # Use a simple serializer with the mixin applied.
        class DummySerializer(CustomFieldsMixin, serializers.Serializer):
            MODEL_NAME = 'product'
            name = serializers.CharField()

            def to_representation(self, instance):
                return {}

        self.serializer = DummySerializer()

    def test_cast_text_returns_as_is(self):
        result = self.serializer._cast_value('hello', self.cf_text)
        self.assertEqual(result, 'hello')

    def test_cast_number_returns_two_decimals(self):
        result = self.serializer._cast_value('12.5', self.cf_number)
        self.assertEqual(result, '12.50')

    def test_cast_number_whole_returns_two_decimals(self):
        result = self.serializer._cast_value('100', self.cf_number)
        self.assertEqual(result, '100.00')

    def test_cast_date_returns_iso_string(self):
        result = self.serializer._cast_value('2025-06-15', self.cf_date)
        self.assertEqual(result, '2025-06-15')

    def test_cast_select_returns_option_string(self):
        result = self.serializer._cast_value('M', self.cf_select)
        self.assertEqual(result, 'M')

    def test_cast_empty_required_returns_empty_string(self):
        result = self.serializer._cast_value('', self.cf_req)
        self.assertEqual(result, '')

    def test_cast_empty_non_required_returns_none(self):
        result = self.serializer._cast_value('', self.cf_text)
        self.assertIsNone(result)

    def test_cast_none_non_required_returns_none(self):
        result = self.serializer._cast_value(None, self.cf_text)
        self.assertIsNone(result)
