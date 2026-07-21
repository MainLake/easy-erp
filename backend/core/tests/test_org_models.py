"""
Phase 1 model unit tests: Organization, Branch, Role, OrganizationMembership.

Spec coverage:
  O1 — Organization CRUD, duplicate tax_id
  O2 — Branch create (with org), orphan rejection
  O3 — Membership join (user ↔ org ↔ role)
  R1 — Role CRUD with valid permission JSON
  R2 — Invalid module/action rejected on Role.clean()
  O6 — Warehouse manager/assistant assignment
"""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.contrib.auth import get_user_model

from core.models import (
    Organization,
    Branch,
    Role,
    OrganizationMembership,
    VALID_MODULES,
    VALID_ACTIONS,
    validate_permissions_schema,
)
from inventory.models import Warehouse

User = get_user_model()


# ---------------------------------------------------------------------------
# Organization — spec O1
# ---------------------------------------------------------------------------

class OrganizationModelTests(TestCase):
    """O1: Organization CRUD, duplicate tax_id rejection."""

    def test_org_create_and_read(self):
        """O1-Create: GIVEN valid data / WHEN creating org / THEN persisted with correct fields."""
        org = Organization.objects.create(
            name='Acme Corp',
            tax_id='TAX-001',
            settings={'timezone': 'UTC'},
        )
        self.assertEqual(org.name, 'Acme Corp')
        self.assertEqual(org.tax_id, 'TAX-001')
        self.assertTrue(org.is_active)
        self.assertEqual(org.settings, {'timezone': 'UTC'})
        self.assertIsNotNone(org.id)
        self.assertIsNotNone(org.created_at)
        self.assertIsNotNone(org.updated_at)

        fetched = Organization.objects.get(pk=org.pk)
        self.assertEqual(fetched.name, 'Acme Corp')

    def test_org_update(self):
        """O1: GIVEN existing org / WHEN updating name / THEN change persists."""
        org = Organization.objects.create(name='Old Name', tax_id='TAX-002')
        org.name = 'New Name'
        org.save()
        org.refresh_from_db()
        self.assertEqual(org.name, 'New Name')

    def test_org_delete(self):
        """O1: GIVEN existing org / WHEN deleting / THEN no longer in database."""
        org = Organization.objects.create(name='To Delete', tax_id='TAX-003')
        pk = org.pk
        org.delete()
        self.assertFalse(Organization.objects.filter(pk=pk).exists())

    def test_duplicate_tax_id_rejected(self):
        """O1-Duplicate: GIVEN org with tax_id='X' / WHEN creating another with tax_id='X' / THEN IntegrityError."""
        Organization.objects.create(name='First', tax_id='TAX-004')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(name='Second', tax_id='TAX-004')

    def test_duplicate_name_rejected(self):
        """O1: GIVEN org with name='UniqueCo' / WHEN creating another with same name / THEN IntegrityError."""
        Organization.objects.create(name='UniqueCo', tax_id='TAX-005')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(name='UniqueCo', tax_id='TAX-006')

    def test_org_str_returns_name(self):
        org = Organization.objects.create(name='Str Org', tax_id='TAX-007')
        self.assertEqual(str(org), 'Str Org')

    def test_org_settings_defaults_to_empty_dict(self):
        org = Organization.objects.create(name='No Settings', tax_id='TAX-008')
        self.assertEqual(org.settings, {})


# ---------------------------------------------------------------------------
# Branch — spec O2
# ---------------------------------------------------------------------------

class BranchModelTests(TestCase):
    """O2: Branch belongs to one organization."""

    def setUp(self):
        self.org = Organization.objects.create(name='Branch Org', tax_id='TAX-100')

    def test_branch_create_with_org(self):
        """O2-Create: GIVEN valid org / WHEN creating branch / THEN 201-pattern (persisted)."""
        branch = Branch.objects.create(
            name='Main Branch',
            address='123 Main St',
            organization=self.org,
        )
        self.assertEqual(branch.name, 'Main Branch')
        self.assertEqual(branch.address, '123 Main St')
        self.assertEqual(branch.organization, self.org)
        self.assertTrue(branch.is_active)
        self.assertIsNotNone(branch.created_at)

    def test_branch_orphan_no_org_rejected(self):
        """O2-Orphan: GIVEN no org / WHEN creating branch / THEN IntegrityError (NOT NULL constraint)."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Branch.objects.create(name='Orphan', address='Nowhere')

    def test_branch_str_includes_org_name(self):
        branch = Branch.objects.create(name='Store 1', organization=self.org)
        self.assertIn('Store 1', str(branch))
        self.assertIn(self.org.name, str(branch))

    def test_branch_unique_per_org(self):
        """O2: GIVEN branch 'Downtown' in org / WHEN creating another 'Downtown' in same org / THEN IntegrityError."""
        Branch.objects.create(name='Downtown', organization=self.org)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Branch.objects.create(name='Downtown', organization=self.org)

    def test_branch_same_name_different_org_ok(self):
        """O2: GIVEN branch 'North' in org A / WHEN creating 'North' in org B / THEN allowed (different orgs)."""
        org_b = Organization.objects.create(name='Org B', tax_id='TAX-101')
        Branch.objects.create(name='North', organization=self.org)
        branch_b = Branch.objects.create(name='North', organization=org_b)
        self.assertEqual(branch_b.organization, org_b)

    def test_branch_related_queryset_from_org(self):
        """O2: branches reverse relation returns correct branches."""
        Branch.objects.create(name='Branch A', organization=self.org)
        Branch.objects.create(name='Branch B', organization=self.org)
        self.assertEqual(self.org.branches.count(), 2)
        self.assertEqual(self.org.branches.filter(name='Branch A').count(), 1)


# ---------------------------------------------------------------------------
# Role — spec R1, R2
# ---------------------------------------------------------------------------

class RoleModelTests(TestCase):
    """R1: Role CRUD with permissions JSON; R2: module/action validation."""

    def setUp(self):
        self.org = Organization.objects.create(name='Role Org', tax_id='TAX-200')
        self.valid_perms = {
            'inventory': ['read', 'write'],
            'sales': ['read'],
        }

    def test_role_create_with_valid_permissions(self):
        """R1-Create: GIVEN valid permissions dict / WHEN creating role / THEN persisted."""
        role = Role.objects.create(
            name='Warehouse Manager',
            organization=self.org,
            permissions=self.valid_perms,
        )
        self.assertEqual(role.name, 'Warehouse Manager')
        self.assertEqual(role.organization, self.org)
        self.assertEqual(role.permissions, self.valid_perms)

    def test_role_default_permissions_is_empty_dict(self):
        role = Role.objects.create(name='Empty Role', organization=self.org)
        self.assertEqual(role.permissions, {})

    def test_role_unique_per_org(self):
        """R1: GIVEN role 'Manager' in org / WHEN creating duplicate / THEN IntegrityError."""
        Role.objects.create(name='Manager', organization=self.org, permissions=self.valid_perms)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(name='Manager', organization=self.org, permissions=self.valid_perms)

    def test_role_same_name_different_org_allowed(self):
        org_b = Organization.objects.create(name='Org B', tax_id='TAX-201')
        Role.objects.create(name='Operator', organization=self.org, permissions=self.valid_perms)
        role_b = Role.objects.create(name='Operator', organization=org_b, permissions=self.valid_perms)
        self.assertEqual(role_b.organization, org_b)

    def test_role_str_includes_name_and_org(self):
        role = Role.objects.create(name='Admin', organization=self.org, permissions=self.valid_perms)
        s = str(role)
        self.assertIn('Admin', s)
        self.assertIn(self.org.name, s)

    # --- Permission validation (spec R2) ---

    def test_validate_permissions_schema_valid(self):
        """R2: Valid permissions dict passes validation."""
        validate_permissions_schema({'inventory': ['read', 'write']})
        validate_permissions_schema({})
        validate_permissions_schema({'sales': ['admin']})

    def test_validate_permissions_schema_invalid_module_rejected(self):
        """R2-Invalid module: GIVEN permissions with 'unknown' module / THEN ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            validate_permissions_schema({'unknown': ['read']})
        self.assertIn('unknown', str(ctx.exception))

    def test_validate_permissions_schema_invalid_action_rejected(self):
        """R2-Invalid action: GIVEN permissions with 'delete' action / THEN ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            validate_permissions_schema({'inventory': ['delete']})
        self.assertIn('delete', str(ctx.exception))

    def test_validate_permissions_schema_non_dict_rejected(self):
        """R2: GIVEN a list instead of dict / THEN ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            validate_permissions_schema(['not', 'a', 'dict'])
        self.assertIn('JSON object', str(ctx.exception))

    def test_validate_permissions_schema_actions_not_list_rejected(self):
        """R2: GIVEN actions as string instead of list / THEN ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            validate_permissions_schema({'inventory': 'read'})
        self.assertIn('must be a list', str(ctx.exception))

    def test_role_clean_rejects_invalid_permissions(self):
        """R2: Role.clean() propagates JSON schema validation."""
        role = Role(
            name='Bad Perms',
            organization=self.org,
            permissions={'bad_module': ['read']},
        )
        with self.assertRaises(ValidationError):
            role.clean()

    def test_role_clean_accepts_valid_permissions(self):
        """R2: Role.clean() passes with valid permissions."""
        role = Role(
            name='Good Perms',
            organization=self.org,
            permissions={'inventory': ['read', 'write', 'admin']},
        )
        role.clean()  # should not raise

    def test_all_known_modules_accepted(self):
        """All four known modules pass validation."""
        perms = {m: ['read'] for m in VALID_MODULES}
        validate_permissions_schema(perms)


# ---------------------------------------------------------------------------
# OrganizationMembership — spec O3
# ---------------------------------------------------------------------------

class OrganizationMembershipModelTests(TestCase):
    """O3: User↔Org via OrganizationMembership; uniqueness, is_default."""

    def setUp(self):
        self.org_a = Organization.objects.create(name='Org A', tax_id='TAX-300')
        self.org_b = Organization.objects.create(name='Org B', tax_id='TAX-301')
        self.role = Role.objects.create(
            name='Member',
            organization=self.org_a,
            permissions={'inventory': ['read']},
        )
        self.role_b = Role.objects.create(
            name='Member',
            organization=self.org_b,
            permissions={'sales': ['read']},
        )
        self.user = User.objects.create_user(
            email='member@easyerp.local',
            password='testpass123',
            full_name='Member User',
        )

    def test_membership_create_join(self):
        """O3-Join: GIVEN user, org, role / WHEN creating membership / THEN persisted."""
        membership = OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org_a,
            role=self.role,
        )
        self.assertEqual(membership.user, self.user)
        self.assertEqual(membership.organization, self.org_a)
        self.assertEqual(membership.role, self.role)
        self.assertTrue(membership.is_active)
        self.assertFalse(membership.is_default)

    def test_membership_user_can_join_multiple_orgs(self):
        """O3: GIVEN user already in org A / WHEN creating membership for org B / THEN allowed."""
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role=self.role,
        )
        membership_b = OrganizationMembership.objects.create(
            user=self.user, organization=self.org_b, role=self.role_b,
        )
        self.assertEqual(self.user.memberships.count(), 2)
        self.assertEqual(membership_b.organization, self.org_b)

    def test_membership_unique_user_org(self):
        """O3: Duplicate (user, org) pair rejected."""
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role=self.role,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    user=self.user, organization=self.org_a, role=self.role,
                )

    def test_membership_str_shows_user_org_role(self):
        membership = OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role=self.role,
        )
        s = str(membership)
        self.assertIn(self.user.email, s)
        self.assertIn(self.org_a.name, s)
        self.assertIn(self.role.name, s)

    def test_membership_is_default_toggle(self):
        """O3: Setting is_default=True clears previous default for same user."""
        m1 = OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role=self.role, is_default=True,
        )
        self.assertTrue(m1.is_default)

        m2 = OrganizationMembership.objects.create(
            user=self.user, organization=self.org_b, role=self.role_b, is_default=True,
        )
        m1.refresh_from_db()
        self.assertFalse(m1.is_default)
        self.assertTrue(m2.is_default)

    def test_membership_role_protected_on_delete(self):
        """Role is PROTECT — deleting a role with memberships should raise."""
        membership = OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role=self.role,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.role.delete()

    # --- User.active_membership ---

    def test_user_active_membership_returns_default(self):
        """active_membership returns the is_default membership."""
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role=self.role,
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_b, role=self.role_b, is_default=True,
        )
        membership = self.user.active_membership
        self.assertEqual(membership.organization, self.org_b)

    def test_user_active_membership_fallback_first(self):
        """When no is_default, active_membership returns the first membership."""
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role=self.role,
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_b, role=self.role_b,
        )
        membership = self.user.active_membership
        self.assertIsNotNone(membership)
        # Just verify it returns one of the two
        self.assertIn(membership.organization, [self.org_a, self.org_b])

    def test_user_active_membership_none_when_no_membership(self):
        """User with no memberships → active_membership is None."""
        fresh_user = User.objects.create_user(
            email='lonely@easyerp.local',
            password='testpass123',
            full_name='Lonely',
        )
        self.assertIsNone(fresh_user.active_membership)

    def test_user_organizations_m2m_through_membership(self):
        """User.organizations M2M returns orgs the user belongs to."""
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_a, role=self.role,
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org_b, role=self.role_b,
        )
        orgs = set(self.user.organizations.all())
        self.assertEqual(orgs, {self.org_a, self.org_b})


# ---------------------------------------------------------------------------
# Warehouse — spec O6 (manager + assistants)
# ---------------------------------------------------------------------------

class WarehouseModelTests(TestCase):
    """O6: Warehouse manager and assistants must be same-org members."""

    def setUp(self):
        self.org = Organization.objects.create(name='Warehouse Org', tax_id='TAX-400')
        self.user = User.objects.create_user(
            email='wm@easyerp.local',
            password='testpass123',
            full_name='Warehouse Manager',
        )
        self.assistant = User.objects.create_user(
            email='assist@easyerp.local',
            password='testpass123',
            full_name='Assistant',
        )

    def test_warehouse_assign_manager(self):
        """O6-Manager: GIVEN warehouse / WHEN assigning manager / THEN persisted."""
        wh = Warehouse.objects.create(
            name='WH-01',
            organization=self.org,
            managed_by=self.user,
        )
        self.assertEqual(wh.managed_by, self.user)
        self.assertIn(wh, self.user.managed_warehouses.all())

    def test_warehouse_manager_can_be_null(self):
        """Warehouse without manager is allowed."""
        wh = Warehouse.objects.create(name='WH-02', organization=self.org)
        self.assertIsNone(wh.managed_by)

    def test_warehouse_add_assistant(self):
        """O6: GIVEN warehouse / WHEN adding assistant / THEN M2M reflects it."""
        wh = Warehouse.objects.create(name='WH-03', organization=self.org)
        wh.assistants.add(self.assistant)
        self.assertIn(self.assistant, wh.assistants.all())
        self.assertIn(wh, self.assistant.assisted_warehouses.all())

    def test_warehouse_multiple_assistants(self):
        """A warehouse can have multiple assistants."""
        u2 = User.objects.create_user(
            email='assist2@easyerp.local',
            password='testpass123',
            full_name='Assistant 2',
        )
        wh = Warehouse.objects.create(name='WH-04', organization=self.org)
        wh.assistants.add(self.assistant, u2)
        self.assertEqual(wh.assistants.count(), 2)

    def test_warehouse_assistants_empty_by_default(self):
        """New warehouse has no assistants initially."""
        wh = Warehouse.objects.create(name='WH-05', organization=self.org)
        self.assertEqual(wh.assistants.count(), 0)

    def test_user_reverse_relations(self):
        """User.managed_warehouses and assisted_warehouses filter correctly."""
        wh1 = Warehouse.objects.create(
            name='WH-A', organization=self.org, managed_by=self.user,
        )
        wh2 = Warehouse.objects.create(name='WH-B', organization=self.org)
        wh2.assistants.add(self.assistant)

        self.assertEqual(self.user.managed_warehouses.count(), 1)
        self.assertEqual(self.user.managed_warehouses.first(), wh1)
        self.assertEqual(self.assistant.assisted_warehouses.count(), 1)
        self.assertEqual(self.assistant.assisted_warehouses.first(), wh2)
