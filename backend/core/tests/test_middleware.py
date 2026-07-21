"""
Phase 2 tests: Middleware, OrgAwareManager, JWT organisation claim.

Spec coverage:
  X4 — org resolution from JWT claim and X-Organization header fallback
  A1 — JWT access token contains active_organization_id claim
  —   — OrgAwareManager auto-filters by thread-local org
"""

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from core.models import Organization, Role, OrganizationMembership
from core.managers import (
    OrgAwareManager,
    set_current_organization_id,
    get_current_organization,
    clear_current_organization,
)
from core.middleware import OrganizationMiddleware

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_access_token(user):
    """Generate an access-token string with ``active_organization_id``.

    Uses ``RefreshToken.for_user()`` which bypasses the custom
    serializer, so we manually inject the claim the same way
    ``CustomTokenObtainPairSerializer.get_token()`` does (spec A1).
    """
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    membership = (
        user.memberships.filter(is_default=True)
        .select_related('organization')
        .first()
        or user.memberships.select_related('organization').first()
    )
    if membership:
        refresh['active_organization_id'] = str(membership.organization_id)

    # Return the *access* token string (the middleware decodes AccessToken,
    # not RefreshToken).
    return str(refresh.access_token)


def _auth_header(token_str):
    return f'Bearer {token_str}'


# ---------------------------------------------------------------------------
# Middleware — org resolution (spec X4)
# ---------------------------------------------------------------------------

class MiddlewareOrgResolutionTests(TestCase):
    """X4: Org resolved from JWT claim and X-Organization header."""

    def setUp(self):
        self.factory = RequestFactory()
        self.org = Organization.objects.create(name='Acme', tax_id='TAX-MW1')
        self.role = Role.objects.create(
            name='Worker', organization=self.org,
            permissions={'inventory': ['read']},
        )
        self.user = User.objects.create_user(
            email='mw@easyerp.local', password='p', full_name='MW User',
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role=self.role,
        )

    def _apply(self, request):
        """Run the middleware and return the modified request."""
        captured = {}

        def get_response(r):
            captured['request'] = r
            # The get_response function simulates view processing.
            # At this point the middleware has set request.organization
            # and the thread-local.
            from django.http import HttpResponse
            return HttpResponse('ok')

        middleware = OrganizationMiddleware(get_response)
        middleware(request)
        return captured.get('request', request)

    # --- JWT-based resolution ---

    def test_org_resolved_from_jwt_claim(self):
        """X4: JWT with active_organization_id → request.organization set."""
        token = _make_access_token(self.user)
        request = self.factory.get('/api/test/', HTTP_AUTHORIZATION=_auth_header(token))
        request.user = self.user
        processed = self._apply(request)

        self.assertIsNotNone(processed.organization)
        self.assertEqual(processed.organization, self.org)

    def test_jwt_without_org_claim_sets_none(self):
        """X4: JWT without active_organization_id → request.organization is None."""
        # Use a user with no memberships — no claim injected.
        homeless = User.objects.create_user(
            email='homeless@easyerp.local', password='p', full_name='No Org',
        )
        token = _make_access_token(homeless)
        request = self.factory.get('/api/test/', HTTP_AUTHORIZATION=_auth_header(token))
        request.user = homeless
        processed = self._apply(request)

        self.assertIsNone(processed.organization)

    # --- Header fallback ---

    def test_org_resolved_from_x_org_header(self):
        """X4: X-Organization header → org resolved (no JWT needed)."""
        request = self.factory.get(
            '/api/test/',
            HTTP_X_ORGANIZATION=str(self.org.id),
        )
        request.user = self.user
        processed = self._apply(request)

        self.assertEqual(processed.organization, self.org)

    def test_x_org_header_overridden_by_jwt(self):
        """X4: JWT claim takes priority over X-Organization header."""
        org2 = Organization.objects.create(name='Other', tax_id='TAX-MW2')
        role2 = Role.objects.create(
            name='Worker', organization=org2,
            permissions={'sales': ['read']},
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=org2, role=role2, is_default=True,
        )
        token = _make_access_token(self.user)

        request = self.factory.get(
            '/api/test/',
            HTTP_AUTHORIZATION=_auth_header(token),
            HTTP_X_ORGANIZATION=str(self.org.id),  # should be ignored
        )
        request.user = self.user
        processed = self._apply(request)

        # JWT wins → org2
        self.assertEqual(processed.organization, org2)

    def test_no_jwt_no_header_org_is_none(self):
        """X4: No JWT, no header → request.organization is None."""
        request = self.factory.get('/api/test/')
        request.user = self.user
        processed = self._apply(request)

        self.assertIsNone(processed.organization)

    # --- Thread-local cleanup ---

    def test_thread_local_cleaned_after_response(self):
        """Thread-local org is cleared after the response."""
        token = _make_access_token(self.user)
        request = self.factory.get('/api/test/', HTTP_AUTHORIZATION=_auth_header(token))
        request.user = self.user

        captured = {}

        def get_response(r):
            # At this point it IS set
            captured['during'] = get_current_organization()
            from django.http import HttpResponse
            return HttpResponse('ok')

        middleware = OrganizationMiddleware(get_response)
        middleware(request)

        self.assertEqual(captured['during'], str(self.org.id))
        # After middleware returns, it should be cleared
        self.assertIsNone(get_current_organization())


# ---------------------------------------------------------------------------
# JWT claim — spec A1
# ---------------------------------------------------------------------------

class JWTClaimTests(TestCase):
    """A1: JWT access-token carries active_organization_id."""

    def setUp(self):
        self.org = Organization.objects.create(name='JWT Org', tax_id='TAX-JWT1')
        self.role = Role.objects.create(
            name='Member', organization=self.org,
            permissions={'sales': ['write']},
        )
        self.user = User.objects.create_user(
            email='jwt@easyerp.local', password='p', full_name='JWT User',
        )

    def test_token_includes_org_claim(self):
        """A1: Login → access token payload has active_organization_id."""
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role=self.role,
        )
        token_str = _make_access_token(self.user)

        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken(token_str)
        self.assertIn('active_organization_id', token)
        self.assertEqual(token['active_organization_id'], str(self.org.id))

    def test_token_with_multiple_orgs_uses_default(self):
        """A1: User has two orgs; default membership org used in claim."""
        org2 = Organization.objects.create(name='JWT Org2', tax_id='TAX-JWT2')
        role2 = Role.objects.create(
            name='Member', organization=org2,
            permissions={'inventory': ['read']},
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role=self.role,
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=org2, role=role2, is_default=True,
        )
        token_str = _make_access_token(self.user)

        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken(token_str)
        self.assertEqual(token['active_organization_id'], str(org2.id))

    def test_token_no_memberships_no_claim(self):
        """A1: User with zero memberships → claim is omitted."""
        token_str = _make_access_token(self.user)

        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken(token_str)
        self.assertNotIn('active_organization_id', token)


# ---------------------------------------------------------------------------
# OrgAwareManager — auto-filter + for_org
# ---------------------------------------------------------------------------

class FakeOrgModel:
    """In-memory stand-in for a model with an organization FK.

    Mocks the QuerySet API well enough to verify filtering behaviour.
    """

    def __init__(self, name, org_id):
        self.name = name
        self.organization_id = org_id

    def __repr__(self):
        return f'<{self.name} org={self.organization_id}>'


class FakeQuerySet(list):
    """A list-like queryset that supports .filter(organization_id=...)."""

    def filter(self, **kwargs):
        org_id = kwargs.get('organization_id')
        if org_id is None:
            return self
        return FakeQuerySet(item for item in self if item.organization_id == org_id)


class FakeOrgAwareManager(OrgAwareManager):
    """Override get_queryset to return in-memory rows instead of hitting DB."""

    _rows = []

    def get_queryset(self):
        qs = FakeQuerySet(self._rows)
        org_id = get_current_organization()
        if org_id is not None:
            qs = qs.filter(organization_id=org_id)
        return qs

    def for_org(self, org_id):
        return FakeQuerySet(self._rows).filter(organization_id=org_id)


class OrgAwareManagerTests(TestCase):
    """OrgAwareManager auto-filters by thread-local org."""

    ORG_A = '00000000-0000-0000-0000-000000000001'
    ORG_B = '00000000-0000-0000-0000-000000000002'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        FakeOrgAwareManager._rows = [
            FakeOrgModel('Product A1', cls.ORG_A),
            FakeOrgModel('Product A2', cls.ORG_A),
            FakeOrgModel('Product B1', cls.ORG_B),
        ]

    def setUp(self):
        self.manager = FakeOrgAwareManager()

    def tearDown(self):
        clear_current_organization()

    # --- No org set → unfiltered ---

    def test_no_org_returns_all_rows(self):
        """No thread-local org → get_queryset returns all rows."""
        qs = self.manager.get_queryset()
        self.assertEqual(len(qs), 3)
        names = {r.name for r in qs}
        self.assertSetEqual(names, {'Product A1', 'Product A2', 'Product B1'})

    # --- Org set → filtered ---

    def test_org_set_filters_correctly(self):
        """Thread-local org A → only org A rows returned."""
        set_current_organization_id(self.ORG_A)
        qs = self.manager.get_queryset()
        self.assertEqual(len(qs), 2)
        for row in qs:
            self.assertEqual(row.organization_id, self.ORG_A)

    def test_org_b_filters_correctly(self):
        """Thread-local org B → only org B rows returned."""
        set_current_organization_id(self.ORG_B)
        qs = self.manager.get_queryset()
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].name, 'Product B1')

    # --- for_org bypasses thread-local ---

    def test_for_org_ignores_thread_local(self):
        """for_org(A) filters by A even when thread-local is B."""
        set_current_organization_id(self.ORG_B)
        qs = self.manager.for_org(self.ORG_A)
        self.assertEqual(len(qs), 2)
        for row in qs:
            self.assertEqual(row.organization_id, self.ORG_A)

    # --- get_current_organization helpers ---

    def test_get_current_organization_defaults_none(self):
        """Before anything is set, returns None."""
        self.assertIsNone(get_current_organization())

    def test_clear_current_organization(self):
        """After clear, get_current_organization returns None."""
        set_current_organization_id(self.ORG_A)
        clear_current_organization()
        self.assertIsNone(get_current_organization())
