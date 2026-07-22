"""
Unit tests for ApprovalRule model and core.approvals gate/authority helpers.

Spec coverage:
  - ApprovalRule model creation + unique_together(organization, order_type)
  - evaluate_gate: zero-rules-configured no-op (backward compat)
  - evaluate_gate: exact-boundary threshold (total == min_amount -> pending)
  - can_approve authority matrix (owner / role match / approver_users / none)
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from core.approvals import can_approve, evaluate_gate
from core.models import ApprovalRule, OrganizationMembership, Role
from core.tests import OrgTestMixin
from inventory.models import Product
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

    def test_min_quantity_and_product_default_to_none(self):
        """GIVEN valid amount-only data / WHEN creating an ApprovalRule
        without min_quantity/product / THEN both default to None."""
        rule = ApprovalRule.objects.create(
            organization=self.org,
            order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        self.assertIsNone(rule.min_quantity)
        self.assertIsNone(rule.product_id)

    def test_deleting_product_referenced_by_rule_is_protected(self):
        """GIVEN an ApprovalRule referencing a Product / WHEN deleting that
        Product / THEN a ProtectedError is raised (on_delete=PROTECT)."""
        product = Product.objects.create(
            sku='PROTECT-SKU-001', name='Protected Widget', cost='5', price='10',
            organization=self.org,
        )
        ApprovalRule.objects.create(
            organization=self.org,
            order_type='sales_order',
            min_amount=Decimal('1000.00'),
            product=product,
        )
        with self.assertRaises(ProtectedError):
            product.delete()

    def test_clean_rejects_product_from_another_org(self):
        """GIVEN a Product belonging to a different organization / WHEN
        ApprovalRule.clean() runs / THEN a ValidationError is raised on
        the 'product' field."""
        from core.models import Organization

        other_org = Organization.objects.create(
            name='Other Org', tax_id='OTHER-ORG-001',
        )
        foreign_product = Product.objects.create(
            sku='FOREIGN-SKU-001', name='Foreign Widget', cost='5', price='10',
            organization=other_org,
        )
        rule = ApprovalRule(
            organization=self.org,
            order_type='sales_order',
            min_amount=Decimal('1000.00'),
            product=foreign_product,
        )
        with self.assertRaises(ValidationError):
            rule.clean()

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


class AndConjunctionMatchingTests(OrgTestMixin, TestCase):
    """core.approvals.evaluate_gate: AND-conjunction over min_amount,
    min_quantity, product. Unset (None) conditions are skipped; ALL set
    conditions must hold for the rule to trigger 'pending'.

    Spec coverage: multi-condition gate scenarios (amount-only regression,
    quantity-only, product-only, combined pairs/triple, product-matches-
    but-quantity-insufficient, zero-conditions-never-matches).
    """

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(
            name='AND Customer', tax_id='AND-TAX-001', organization=self.org,
        )
        self.user = self.create_org_user('and-user@easyerp.local')
        self.product_p = Product.objects.create(
            sku='AND-SKU-P', name='Product P', cost='5', price='100',
            organization=self.org,
        )
        self.product_other = Product.objects.create(
            sku='AND-SKU-OTHER', name='Other Product', cost='5', price='50',
            organization=self.org,
        )

    def _make_so(self):
        return SalesOrder.objects.create(
            customer=self.customer, organization=self.org,
        )

    def _add_line(self, so, product, quantity, unit_price):
        so.line_items.create(
            product=product, quantity=quantity, unit_price=unit_price,
            warehouse=self.warehouse,
        )

    def test_amount_only_rule_regression_guard(self):
        """GIVEN an amount-only rule (min_quantity=None, product=None) /
        WHEN order total is above/below min_amount / THEN behavior is
        byte-for-byte identical to the pre-existing amount-only gate:
        blocks at/above threshold, proceeds below."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1000.00'),
        )
        blocked_so = self._make_so()
        self._add_line(blocked_so, self.product_p, 10, Decimal('100.00'))  # total=1000
        result = evaluate_gate(order=blocked_so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'pending')

        proceeding_so = self._make_so()
        self._add_line(proceeding_so, self.product_p, 5, Decimal('100.00'))  # total=500
        result = evaluate_gate(order=proceeding_so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'not_required')

    def test_quantity_only_rule_blocks_on_total_quantity(self):
        """GIVEN a quantity-only rule (min_amount=None, product=None) /
        WHEN order total_quantity >= min_quantity / THEN it blocks; below
        threshold it proceeds."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=None, min_quantity=50,
        )
        blocked_so = self._make_so()
        self._add_line(blocked_so, self.product_p, 60, Decimal('1.00'))
        result = evaluate_gate(order=blocked_so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'pending')

        proceeding_so = self._make_so()
        self._add_line(proceeding_so, self.product_p, 10, Decimal('1.00'))
        result = evaluate_gate(order=proceeding_so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'not_required')

    def test_product_only_rule_blocks_when_any_line_matches(self):
        """GIVEN a product-only rule (min_amount=None, min_quantity=None) /
        WHEN any line item among several references the product / THEN it
        blocks."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=None, product=self.product_p,
        )
        so = self._make_so()
        self._add_line(so, self.product_other, 3, Decimal('50.00'))
        self._add_line(so, self.product_p, 1, Decimal('100.00'))
        result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'pending')

    def test_amount_and_quantity_combined(self):
        """GIVEN amount+quantity rule / WHEN both satisfied / THEN blocks;
        WHEN quantity unmet / THEN proceeds (AND semantics)."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1000.00'), min_quantity=50,
        )
        blocked_so = self._make_so()
        self._add_line(blocked_so, self.product_p, 60, Decimal('25.00'))  # total=1500, qty=60
        result = evaluate_gate(order=blocked_so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'pending')

        proceeding_so = self._make_so()
        self._add_line(proceeding_so, self.product_p, 10, Decimal('150.00'))  # total=1500, qty=10
        result = evaluate_gate(order=proceeding_so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'not_required')

    def test_amount_and_product_combined(self):
        """GIVEN amount+product rule / WHEN both satisfied / THEN blocks."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1000.00'), product=self.product_p,
        )
        so = self._make_so()
        self._add_line(so, self.product_p, 15, Decimal('100.00'))  # total=1500
        result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'pending')

    def test_all_three_conditions_combined(self):
        """GIVEN amount+quantity+product rule / WHEN all satisfied / THEN
        blocks."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=Decimal('1000.00'), min_quantity=50, product=self.product_p,
        )
        so = self._make_so()
        self._add_line(so, self.product_p, 60, Decimal('25.00'))  # total=1500, qty=60
        result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'pending')

    def test_product_matches_but_quantity_insufficient_does_not_trigger(self):
        """GIVEN min_quantity+product rule (no min_amount) / WHEN the order
        contains the product but the product-scoped quantity is below
        min_quantity / THEN the rule does NOT trigger (proves AND, not
        OR — product presence alone is insufficient)."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=None, min_quantity=50, product=self.product_p,
        )
        so = self._make_so()
        self._add_line(so, self.product_p, 5, Decimal('100.00'))
        result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'not_required')
        so.refresh_from_db()
        self.assertEqual(so.approval_status, 'none')

    def test_zero_conditions_set_rule_never_matches(self):
        """GIVEN a rule with min_amount=None, min_quantity=None,
        product=None / WHEN evaluated against any order, including one
        with a large total / THEN it never matches."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=None,
        )
        so = self._make_so()
        self._add_line(so, self.product_p, 100, Decimal('1000.00'))  # total=100000
        result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'not_required')
        so.refresh_from_db()
        self.assertEqual(so.approval_status, 'none')

    def test_product_scoped_quantity_ignores_other_lines(self):
        """GIVEN min_quantity+product rule / WHEN the product line meets
        the threshold but is mixed with an unrelated high-quantity line /
        THEN the product-scoped sum (not the order-wide total_quantity)
        determines the match — proves scoping, not just presence."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order',
            min_amount=None, min_quantity=50, product=self.product_p,
        )
        so = self._make_so()
        self._add_line(so, self.product_p, 20, Decimal('10.00'))
        self._add_line(so, self.product_other, 1000, Decimal('1.00'))
        result = evaluate_gate(order=so, order_type='sales_order', user=self.user)
        self.assertEqual(result, 'not_required')


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
