"""Signal handlers for OrganizationMembership — at-least-one-owner invariant.

The ``pre_delete`` handler catches bulk deletions (e.g. ``queryset.delete()``)
that bypass ``Model.save()``.  Together with the ``save()`` override on the
model, this guarantees the invariant at every mutation path (spec O2/O6).
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import OrganizationMembership


@receiver(pre_delete, sender=OrganizationMembership)
def enforce_last_owner_on_delete(sender, instance, **kwargs):
    """Prevent deletion of the last owner membership in an organization.

    Uses ``all_objects`` so the check works regardless of the active
    request-org thread-local (which may be None during bulk operations).
    """
    if not instance.is_owner:
        return  # Not an owner — nothing to check.

    remaining = (
        OrganizationMembership.all_objects
        .filter(
            organization_id=instance.organization_id,
            is_owner=True,
        )
        .exclude(pk=instance.pk)
        .exists()
    )

    if not remaining:
        raise ValidationError(
            'Cannot remove the last owner of the organization.'
        )
