"""
Integration tests for ApprovalRuleViewSet CRUD authorization.

Spec coverage: ApprovalRule model and CRUD authorization — owner OR
`core:admin` may create/update/destroy; any authenticated member may
list/retrieve.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from core.models import ApprovalRule, Role
from core.tests import OrgTestMixin


class ApprovalRuleViewSetPermissionTests(OrgTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin_role = Role.objects.create(
            name='Core Admin Role', organization=self.org,
            permissions={'core': ['admin']},
        )
        self.plain_role = Role.objects.create(
            name='Plain Role', organization=self.org,
            permissions={'sales': ['admin']},
        )

    def _payload(self):
        return {
            'order_type': 'sales_order',
            'min_amount': '1000.00',
        }

    def test_owner_can_create_rule(self):
        """Owner (is_owner=True, no core:admin) can create a rule."""
        owner = self.create_org_user('rule-owner@easyerp.local', role=self.plain_role)
        membership = owner.memberships.get(organization=self.org)
        membership.is_owner = True
        membership.save()

        client = APIClient()
        self._login(client, owner)
        resp = client.post('/api/v1/approval-rules/', self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_core_admin_can_create_rule(self):
        """Non-owner user holding core:admin can create a rule."""
        admin_user = self.create_org_user('rule-admin@easyerp.local', role=self.admin_role)

        client = APIClient()
        self._login(client, admin_user)
        resp = client.post('/api/v1/approval-rules/', self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_non_admin_non_owner_create_rejected(self):
        """A member who is neither owner nor core:admin gets 403 on create."""
        member = self.create_org_user('rule-member@easyerp.local', role=self.plain_role)

        client = APIClient()
        self._login(client, member)
        resp = client.post('/api/v1/approval-rules/', self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ApprovalRule.objects.filter(organization=self.org).exists())

    def test_any_member_can_list(self):
        """A member without owner/core:admin authority can still GET the list."""
        ApprovalRule.objects.create(
            organization=self.org, order_type='sales_order', min_amount=Decimal('500.00'),
        )
        member = self.create_org_user('rule-viewer@easyerp.local', role=self.plain_role)

        client = APIClient()
        self._login(client, member)
        resp = client.get('/api/v1/approval-rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
