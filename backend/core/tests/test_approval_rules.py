"""
Unit tests for ApprovalRule model and core.approvals gate/authority helpers.

Spec coverage:
  - ApprovalRule model creation + unique_together(organization, order_type)
  - evaluate_gate: zero-rules-configured no-op (backward compat)
  - evaluate_gate: exact-boundary threshold (total == min_amount -> pending)
  - can_approve authority matrix (owner / role match / approver_users / none)
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from core.approvals import can_approve, evaluate_gate
from core.models import ApprovalRule, OrganizationMembership, Role
from core.tests import OrgTestMixin
from sales.models import Customer, SalesOrder


class ApprovalRuleModelTests(OrgTestMixin, TestCase):
    """ApprovalRule model: creation and unique_together enforcement."""

    def test_create_approval_rule(self):
        """GIVEN valid data / WHEN creating an ApprovalRule / THEN persisted."""
        rule = ApprovalRule.objects.create(
            organization=self.org,
            order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        self.assertEqual(rule.order_type, 'sales_order')
        self.assertEqual(rule.min_amount, Decimal('1000.00'))
        self.assertTrue(rule.is_active)
        self.assertIsNotNone(rule.id)

    def test_duplicate_order_type_per_org_rejected(self):
        """GIVEN an existing rule for (org, order_type) / WHEN creating a
        second rule for the same pair / THEN IntegrityError is raised."""
        ApprovalRule.objects.create(
            organization=self.org,
            order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ApprovalRule.objects.create(
                    organization=self.org,
                    order_type='sales_order',
                    min_amount=Decimal('2000.00'),
                )


class EvaluateGateTests(OrgTestMixin, TestCase):
    """core.approvals.evaluate_gate: zero-rule no-op and boundary behavior."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(
            name='Gate Customer', tax_id='GATE-TAX-001', organization=self.org,
        )
        self.user = self.create_org_user('gate-user@easyerp.local')

    def _make_so(self):
        return SalesOrder.objects.create(
            customer=self.customer, organization=self.org,
        )

    def test_no_active_rule_returns_not_required_and_commits(self):
        """GIVEN no ApprovalRule exists for this org/order_type / WHEN
        evaluate_gate runs inside an atomic block / THEN it returns
        'not_required' without raising, and the caller's write commits."""
        so = self._make_so()
        with transaction.atomic():
            result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
            so.notes = 'touched inside gate call'
            so.save()

        self.assertEqual(result, 'not_required')
        so.refresh_from_db()
        self.assertEqual(so.notes, 'touched inside gate call')
        self.assertEqual(so.approval_status, 'none')

    def test_total_exactly_at_threshold_requires_approval(self):
        """GIVEN an active rule with min_amount=1000 / WHEN order total is
        exactly 1000 (derived from line items) / THEN evaluate_gate returns
        'pending' and stamps approval_status + requested_by."""
        from inventory.models import Product

        ApprovalRule.objects.create(
            organization=self.org,
            order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        product = Product.objects.create(
            sku='GATE-SKU-001', name='Widget', cost='5', price='100',
            organization=self.org,
        )
        so = self._make_so()
        so.line_items.create(
            product=product, quantity=10, unit_price=Decimal('100.00'),
            warehouse=self.warehouse,
        )
        result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'pending')
        so.refresh_from_db()
        self.assertEqual(so.approval_status, 'pending')
        self.assertEqual(so.requested_by_id, self.user.id)

    def test_total_below_threshold_not_required(self):
        """GIVEN an active rule with min_amount=1000 / WHEN order total is
        999.99 / THEN evaluate_gate returns 'not_required' and does not
        stamp approval_status (triangulates the boundary case)."""
        from inventory.models import Product

        ApprovalRule.objects.create(
            organization=self.org,
            order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        product = Product.objects.create(
            sku='GATE-SKU-002', name='Gizmo', cost='5', price='9.9999',
            organization=self.org,
        )
        so = self._make_so()
        so.line_items.create(
            product=product, quantity=1, unit_price=Decimal('999.99'),
            warehouse=self.warehouse,
        )
        result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'not_required')
        so.refresh_from_db()
        self.assertEqual(so.approval_status, 'none')


class CanApproveTests(OrgTestMixin, TestCase):
    """core.approvals.can_approve authority matrix."""

    def setUp(self):
        super().setUp()
        self.approver_role = Role.objects.create(
            name='Approver Role',
            organization=self.org,
            permissions={},
        )
        self.other_role = Role.objects.create(
            name='Other Role',
            organization=self.org,
            permissions={},
        )

    def _membership_for(self, user):
        return OrganizationMembership.objects.get(user=user, organization=self.org)

    def test_owner_always_authorized(self):
        """GIVEN a user with is_owner=True / WHEN checked against a rule
        naming a different role / THEN can_approve returns True."""
        owner = self.create_org_user('owner@easyerp.local', role=self.other_role)
        membership = self._membership_for(owner)
        membership.is_owner = True
        membership.save()
        rule = ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1'), approver_role=self.approver_role,
        )
        self.assertTrue(can_approve(owner, self.org, rule))

    def test_role_match_authorized(self):
        """GIVEN a non-owner user whose membership role equals the rule's
        approver_role / THEN can_approve returns True."""
        member = self.create_org_user(
            'role-match@easyerp.local', role=self.approver_role,
        )
        rule = ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1'), approver_role=self.approver_role,
        )
        self.assertTrue(can_approve(member, self.org, rule))

    def test_approver_users_membership_authorized(self):
        """GIVEN a non-owner user listed in approver_users / THEN
        can_approve returns True even without a matching role."""
        member = self.create_org_user(
            'listed-user@easyerp.local', role=self.other_role,
        )
        rule = ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1'), approver_role=self.approver_role,
        )
        rule.approver_users.add(member)
        self.assertTrue(can_approve(member, self.org, rule))

    def test_unrelated_user_not_authorized(self):
        """GIVEN a non-owner user matching none of the authority criteria
        / THEN can_approve returns False."""
        member = self.create_org_user(
            'unrelated@easyerp.local', role=self.other_role,
        )
        rule = ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1'), approver_role=self.approver_role,
        )
        self.assertFalse(can_approve(member, self.org, rule))
