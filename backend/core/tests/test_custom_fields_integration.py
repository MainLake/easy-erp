"""
Integration tests: custom_fields flow through entity serializers.

Verifies that CustomFieldsMixin applied to ProductSerializer, CustomerSerializer,
SupplierSerializer, and OrganizationSerializer correctly:
  - Accepts custom_fields on create
  - Returns custom_fields on read
  - Persists and returns updated custom_fields on update
  - Rejects invalid types with 400
  - Handles empty custom_fields payload gracefully
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from core.models import CustomField, CustomFieldValue, Organization
from core.tests import OrgTestMixin


class CustomFieldsIntegrationTests(OrgTestMixin, TestCase):
    """Entity integration: create/read/update with custom_fields payloads."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

        # User with full permissions on all modules
        self.user = self.create_org_user('cf-integration@test.com')
        self._login(self.client, self.user)

        # Org owner — needed for organization PATCH (IsOrgOwner perm)
        from django.contrib.auth import get_user_model
        from core.models import OrganizationMembership
        User = get_user_model()
        self.owner = User.objects.create_user(
            email='cf-owner-int@test.com', password='testpass123',
            full_name='Owner',
        )
        OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, role=self.role,
            is_owner=True, is_default=True,
        )

        # — product custom fields —
        self.cf_product_grade = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Grade', field_type='select',
            options=['A', 'B', 'C'], required=False, order=1,
        )
        self.cf_product_weight = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Weight', field_type='number', required=False, order=2,
        )
        self.cf_product_notes = CustomField.objects.create(
            organization=self.org, model_name='product',
            name='Notes', field_type='text', required=False, order=3,
        )

        # — customer custom fields —
        self.cf_customer_contact = CustomField.objects.create(
            organization=self.org, model_name='customer',
            name='ContactPerson', field_type='text', required=False, order=1,
        )
        self.cf_customer_credit = CustomField.objects.create(
            organization=self.org, model_name='customer',
            name='CreditLimit', field_type='number', required=False, order=2,
        )

        # — supplier custom fields —
        self.cf_supplier_contact = CustomField.objects.create(
            organization=self.org, model_name='supplier',
            name='MainContact', field_type='text', required=False, order=1,
        )
        self.cf_supplier_terms = CustomField.objects.create(
            organization=self.org, model_name='supplier',
            name='PaymentTerms', field_type='text', required=False, order=2,
        )

        # — organization custom fields —
        self.cf_org_industry = CustomField.objects.create(
            organization=self.org, model_name='organization',
            name='Industry', field_type='text', required=False, order=1,
        )
        self.cf_org_employees = CustomField.objects.create(
            organization=self.org, model_name='organization',
            name='EmployeeCount', field_type='number', required=False, order=2,
        )

    # =====================================================================
    # Product — create, read, update with custom_fields
    # =====================================================================

    def test_product_create_with_custom_fields(self):
        """GIVEN custom field definitions / WHEN POST product with
        custom_fields / THEN response includes cast custom_fields."""
        response = self.client.post('/api/v1/inventory/products/', {
            'sku': 'SKU-001',
            'name': 'Widget',
            'description': 'A test widget',
            'cost': '10.00',
            'price': '25.00',
            'custom_fields': {
                'Grade': 'A',
                'Weight': '12.5',
                'Notes': 'First batch',
            },
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         f'Create failed: {response.data}')
        cf = response.data['custom_fields']
        self.assertEqual(cf['Grade'], 'A')
        self.assertEqual(cf['Weight'], '12.50')
        self.assertEqual(cf['Notes'], 'First batch')

    def test_product_read_returns_custom_fields(self):
        """GIVEN product created with custom_fields / WHEN GET detail /
        THEN custom_fields are returned."""
        create_resp = self.client.post('/api/v1/inventory/products/', {
            'sku': 'SKU-002',
            'name': 'Gadget',
            'cost': '5.00',
            'price': '15.00',
            'custom_fields': {'Grade': 'B', 'Weight': '3'},
        }, format='json')
        product_id = create_resp.data['id']

        response = self.client.get(f'/api/v1/inventory/products/{product_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cf = response.data['custom_fields']
        self.assertEqual(cf['Grade'], 'B')
        self.assertEqual(cf['Weight'], '3.00')

    def test_product_update_custom_fields(self):
        """GIVEN product with custom_fields / WHEN PATCH with new
        custom_fields / THEN values are updated in response."""
        create_resp = self.client.post('/api/v1/inventory/products/', {
            'sku': 'SKU-003',
            'name': 'Thingamajig',
            'cost': '8.00',
            'price': '20.00',
            'custom_fields': {'Notes': 'Original note'},
        }, format='json')
        product_id = create_resp.data['id']
        self.assertEqual(create_resp.data['custom_fields']['Notes'], 'Original note')

        # Update custom_fields
        patch_resp = self.client.patch(
            f'/api/v1/inventory/products/{product_id}/',
            {'custom_fields': {'Notes': 'Updated note', 'Grade': 'C'}},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        cf = patch_resp.data['custom_fields']
        self.assertEqual(cf['Notes'], 'Updated note')
        self.assertEqual(cf['Grade'], 'C')

    def test_product_update_without_custom_fields_preserves(self):
        """GIVEN product with custom_fields / WHEN PATCH without
        custom_fields key / THEN existing values preserved."""
        create_resp = self.client.post('/api/v1/inventory/products/', {
            'sku': 'SKU-004',
            'name': 'Doodad',
            'cost': '3.00',
            'price': '9.00',
            'custom_fields': {'Notes': 'Keep me'},
        }, format='json')
        product_id = create_resp.data['id']

        # Patch only name — no custom_fields
        self.client.patch(
            f'/api/v1/inventory/products/{product_id}/',
            {'name': 'Doodad Updated'},
            format='json',
        )

        # Read back — custom_fields should still be there
        response = self.client.get(f'/api/v1/inventory/products/{product_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['custom_fields']['Notes'], 'Keep me')

    def test_product_invalid_number_rejected(self):
        """GIVEN number custom field / WHEN non-numeric submitted /
        THEN 400 with field-level error in envelope."""
        response = self.client.post('/api/v1/inventory/products/', {
            'sku': 'SKU-005',
            'name': 'Bad Widget',
            'cost': '5.00',
            'price': '10.00',
            'custom_fields': {'Weight': 'large'},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data['errors'])
        self.assertTrue(any(
            'Weight' in e.get('message', '')
            for e in response.data['errors']
        ))

    # =====================================================================
    # Customer — create, read, update with custom_fields
    # =====================================================================

    def test_customer_create_with_custom_fields(self):
        """GIVEN customer field definitions / WHEN POST customer with
        custom_fields / THEN response includes them."""
        response = self.client.post('/api/v1/sales/customers/', {
            'name': 'ACME Corp',
            'tax_id': 'TAX-001',
            'contact': 'John Doe',
            'custom_fields': {
                'ContactPerson': 'Jane Smith',
                'CreditLimit': '50000',
            },
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         f'Create failed: {response.data}')
        cf = response.data['custom_fields']
        self.assertEqual(cf['ContactPerson'], 'Jane Smith')
        self.assertEqual(cf['CreditLimit'], '50000.00')

    def test_customer_read_returns_custom_fields(self):
        """GIVEN customer with custom_fields / WHEN GET / THEN returned."""
        create_resp = self.client.post('/api/v1/sales/customers/', {
            'name': 'Globex Inc',
            'tax_id': 'TAX-002',
            'custom_fields': {'CreditLimit': '75000'},
        }, format='json')
        customer_id = create_resp.data['id']

        response = self.client.get(f'/api/v1/sales/customers/{customer_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['custom_fields']['CreditLimit'], '75000.00')

    def test_customer_update_custom_fields(self):
        """GIVEN customer / WHEN PATCH new custom_fields / THEN updated."""
        create_resp = self.client.post('/api/v1/sales/customers/', {
            'name': 'Initech',
            'tax_id': 'TAX-003',
            'custom_fields': {'ContactPerson': 'Bob'},
        }, format='json')
        customer_id = create_resp.data['id']

        patch_resp = self.client.patch(
            f'/api/v1/sales/customers/{customer_id}/',
            {'custom_fields': {'ContactPerson': 'Alice', 'CreditLimit': '25000'}},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        cf = patch_resp.data['custom_fields']
        self.assertEqual(cf['ContactPerson'], 'Alice')
        self.assertEqual(cf['CreditLimit'], '25000.00')

    # =====================================================================
    # Supplier — create, read, update with custom_fields
    # =====================================================================

    def test_supplier_create_with_custom_fields(self):
        """GIVEN supplier field definitions / WHEN POST supplier with
        custom_fields / THEN response includes them."""
        response = self.client.post('/api/v1/purchasing/suppliers/', {
            'name': 'Parts Co',
            'tax_id': 'TAX-SUP-001',
            'contact': 'Supply Chain',
            'custom_fields': {
                'MainContact': 'Mary',
                'PaymentTerms': 'Net 30',
            },
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         f'Create failed: {response.data}')
        cf = response.data['custom_fields']
        self.assertEqual(cf['MainContact'], 'Mary')
        self.assertEqual(cf['PaymentTerms'], 'Net 30')

    def test_supplier_read_returns_custom_fields(self):
        """GIVEN supplier with custom_fields / WHEN GET / THEN returned."""
        create_resp = self.client.post('/api/v1/purchasing/suppliers/', {
            'name': 'Materials Ltd',
            'tax_id': 'TAX-SUP-002',
            'custom_fields': {'PaymentTerms': 'Net 60'},
        }, format='json')
        supplier_id = create_resp.data['id']

        response = self.client.get(f'/api/v1/purchasing/suppliers/{supplier_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['custom_fields']['PaymentTerms'], 'Net 60')

    def test_supplier_update_custom_fields(self):
        """GIVEN supplier / WHEN PATCH new custom_fields / THEN updated."""
        create_resp = self.client.post('/api/v1/purchasing/suppliers/', {
            'name': 'Vendor Inc',
            'tax_id': 'TAX-SUP-003',
            'custom_fields': {'MainContact': 'Old Contact'},
        }, format='json')
        supplier_id = create_resp.data['id']

        patch_resp = self.client.patch(
            f'/api/v1/purchasing/suppliers/{supplier_id}/',
            {'custom_fields': {'MainContact': 'New Contact'}},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            patch_resp.data['custom_fields']['MainContact'], 'New Contact',
        )

    # =====================================================================
    # Organization — apply custom_fields to organization
    # =====================================================================

    def test_organization_returns_custom_fields(self):
        """GIVEN organization custom field definitions / WHEN GET org /
        THEN custom_fields injected in response for the current org."""
        # Set values on the current org
        CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='organization',
            entity_id=self.org.id,
            field=self.cf_org_industry,
            value='Manufacturing',
        )
        CustomFieldValue.objects.create(
            organization=self.org,
            entity_type='organization',
            entity_id=self.org.id,
            field=self.cf_org_employees,
            value='250',
        )

        response = self.client.get(f'/api/v1/orgs/{self.org.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cf = response.data['custom_fields']
        self.assertEqual(cf['Industry'], 'Manufacturing')
        self.assertEqual(cf['EmployeeCount'], '250.00')

    def test_organization_update_custom_fields(self):
        """GIVEN organization / WHEN PATCH with custom_fields / THEN
        values are persisted."""
        self._login(self.client, self.owner)
        patch_resp = self.client.patch(
            f'/api/v1/orgs/{self.org.id}/',
            {'custom_fields': {
                'Industry': 'Technology',
                'EmployeeCount': '42',
            }},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        cf = patch_resp.data['custom_fields']
        self.assertEqual(cf['Industry'], 'Technology')
        self.assertEqual(cf['EmployeeCount'], '42.00')

        # Verify persisted in DB
        value = CustomFieldValue.objects.get(
            organization=self.org,
            entity_type='organization',
            entity_id=self.org.id,
            field=self.cf_org_industry,
        )
        self.assertEqual(value.value, 'Technology')

    # =====================================================================
    # Edge cases
    # =====================================================================

    def test_create_with_empty_custom_fields(self):
        """GIVEN no custom_fields key / WHEN POST product / THEN no error,
        custom_fields blank for all defined fields."""
        response = self.client.post('/api/v1/inventory/products/', {
            'sku': 'SKU-EMPTY',
            'name': 'No Fields',
            'cost': '1.00',
            'price': '2.00',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         f'Create failed: {response.data}')
        # to_representation returns all defined fields with None when no values set
        cf = response.data['custom_fields']
        self.assertIn('Notes', cf)
        self.assertIsNone(cf['Notes'])

    def test_unknown_field_name_silently_dropped(self):
        """GIVEN a field name with no definition / WHEN submitted /
        THEN silently dropped, valid fields still persisted."""
        response = self.client.post('/api/v1/inventory/products/', {
            'sku': 'SKU-DROP',
            'name': 'Drop Unknown',
            'cost': '1.00',
            'price': '2.00',
            'custom_fields': {
                'NOPE': 'garbage',       # unknown — dropped
                'Notes': 'Valid note',    # known — kept
            },
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         f'Create failed: {response.data}')
        cf = response.data['custom_fields']
        self.assertNotIn('NOPE', cf)
        self.assertEqual(cf['Notes'], 'Valid note')

    def test_cross_model_isolation(self):
        """GIVEN product with custom_fields / WHEN customer custom_fields
        defined / THEN product custom_fields do not leak into customer."""
        # Create product with custom_fields
        create_resp = self.client.post('/api/v1/inventory/products/', {
            'sku': 'SKU-ISO',
            'name': 'Isolation Test',
            'cost': '1.00',
            'price': '2.00',
            'custom_fields': {'Grade': 'A', 'Notes': 'Product note'},
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)

        # Create customer — should only see customer fields
        customer_resp = self.client.post('/api/v1/sales/customers/', {
            'name': 'Isolation Corp',
            'tax_id': 'TAX-ISO',
            'custom_fields': {'CreditLimit': '99999'},
        }, format='json')
        self.assertEqual(customer_resp.status_code, status.HTTP_201_CREATED)

        # Customer custom_fields should NOT contain product fields
        cf = customer_resp.data['custom_fields']
        self.assertNotIn('Grade', cf)
        self.assertNotIn('Notes', cf)
        self.assertIn('CreditLimit', cf)
