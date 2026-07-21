"""OrganizationMiddleware: resolve active org from JWT or X-Organization header.

Resolves the active organization for each HTTP request and makes it
available via ``request.organization`` (an ``Organization`` instance)
and a thread-local variable consumed by ``OrgAwareManager``.

Resolution order (spec X4):
    1. JWT claim ``active_organization_id`` from the Bearer token
    2. ``X-Organization`` HTTP header (fallback for service-to-service
       and debug calls)

The middleware runs *after*
``django.contrib.auth.middleware.AuthenticationMiddleware`` so
``request.user`` is available, but DRF's ``JWTAuthentication`` hasn't
run yet at this point, so we decode the raw Bearer token ourselves.
"""

from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .managers import clear_current_organization, set_current_organization_id
from .models import Organization


class OrganizationMiddleware:
    """Resolve and stash the active organization for the current request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org_id = self._resolve_org_id(request)

        request.organization = None
        if org_id:
            set_current_organization_id(org_id)
            try:
                request.organization = Organization.objects.get(pk=org_id)
            except Organization.DoesNotExist:
                pass

        response = self.get_response(request)
        clear_current_organization()
        return response

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_org_id(request):
        """Return the org ID (UUID string) or *None*.

        Resolution order:
            1. JWT ``active_organization_id`` claim (spec X4)
            2. ``X-Organization`` HTTP header fallback
        """
        # 1 — JWT Bearer token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            raw_token = auth_header[7:]
            try:
                token = AccessToken(raw_token)
                org_id = token.get('active_organization_id')
                if org_id:
                    return str(org_id)
            except (InvalidToken, TokenError):
                pass

        # 2 — X-Organization header fallback
        return request.headers.get('X-Organization')
