"""Management command to backfill is_owner on existing memberships.

For every organization that has no owner membership yet, marks the
*oldest* membership (by ``created_at``) as ``is_owner=True``.

Usage::

    python manage.py backfill_owners

The command is idempotent — running it multiple times produces the
same result (orgs that already have an owner are skipped).
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, Min

from core.models import Organization, OrganizationMembership


class Command(BaseCommand):
    help = 'Backfill is_owner=True on the oldest membership of each org.'

    def handle(self, *args, **options):
        # Find orgs that already have at least one owner
        orgs_with_owner = (
            OrganizationMembership.all_objects
            .filter(is_owner=True)
            .values_list('organization_id', flat=True)
            .distinct()
        )

        # Find the oldest membership per org — only orgs without an owner
        memberships_to_update = (
            OrganizationMembership.all_objects
            .exclude(organization_id__in=orgs_with_owner)
            .values('organization_id')
            .annotate(oldest=Min('created_at'))
        )

        updated = 0
        skipped = 0

        for entry in memberships_to_update:
            membership = (
                OrganizationMembership.all_objects
                .filter(
                    organization_id=entry['organization_id'],
                    created_at=entry['oldest'],
                )
                .first()
            )
            if membership:
                membership.is_owner = True
                membership.save(update_fields=['is_owner'])
                updated += 1

        skipped = Organization.objects.count() - updated

        self.stdout.write(
            self.style.SUCCESS(
                f'Backfill complete: {updated} org(s) updated, '
                f'{skipped} org(s) already had owners or no memberships.'
            )
        )
