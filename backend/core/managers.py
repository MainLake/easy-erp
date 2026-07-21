"""Org-aware manager with thread-local organization context.

The ``OrganizationMiddleware`` sets the active organization on a
thread-local variable.  ``OrgAwareManager.get_queryset()`` reads that
value and auto-filters every queryset by ``organization_id``.

For models where the org FK field is named differently (e.g.
``core_organization``), use ``CoreOrgAwareManager`` instead.

Usage::

    class Product(BaseModel):
        organization = models.ForeignKey(Organization, ...)
        objects = OrgAwareManager()

    class Invoice(BaseModel):
        core_organization = models.ForeignKey(Organization, ...)
        objects = CoreOrgAwareManager()

"""

import threading

from django.db import models

# ---------------------------------------------------------------------------
# Thread-local storage — one active organisation per request thread
# ---------------------------------------------------------------------------

_org_context = threading.local()


def set_current_organization_id(org_id):
    """Store the active org ID (UUID string) for the current request thread."""
    _org_context.active_org_id = org_id


def get_current_organization():
    """Return the active org ID (UUID string) or *None*."""
    return getattr(_org_context, 'active_org_id', None)


def clear_current_organization():
    """Remove the active org ID from the thread-local store."""
    if hasattr(_org_context, 'active_org_id'):
        del _org_context.active_org_id


# ---------------------------------------------------------------------------
# OrgAwareManager — filters on ``organization_id`` (default)
# ---------------------------------------------------------------------------

class OrgAwareManager(models.Manager):
    """Model manager that auto-filters querysets by the active organization.

    When a thread-local organization is set (by
    ``OrganizationMiddleware``), ``get_queryset()`` automatically adds
    ``.filter(organization_id=...)``.  When no organization is set the
    full queryset is returned — useful for migrations, management
    commands, and cross-org admin views.

    The explicit ``for_org(org_id)`` method allows callers to bypass the
    thread-local when needed.
    """

    _org_filter_field = 'organization'

    def get_queryset(self):
        qs = super().get_queryset()
        org_id = get_current_organization()
        if org_id is not None:
            qs = qs.filter(**{f'{self._org_filter_field}_id': org_id})
        return qs

    def for_org(self, org_id):
        """Return a queryset explicitly scoped to *org_id*, ignoring the
        thread-local store."""
        return super().get_queryset().filter(
            **{f'{self._org_filter_field}_id': org_id},
        )


# ---------------------------------------------------------------------------
# CoreOrgAwareManager — filters on ``core_organization_id``
# ---------------------------------------------------------------------------

class CoreOrgAwareManager(OrgAwareManager):
    """Variant of OrgAwareManager that filters on ``core_organization_id``.

    Used by models where the org-scoping FK is named ``core_organization``
    instead of ``organization`` (e.g. Invoice in the invoicing app, which
    already has an ``organization`` FK pointing to an app-local model).
    """

    _org_filter_field = 'core_organization'
