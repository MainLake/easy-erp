# Generated manually for multi-org-rbac Phase 3.
"""Create a default Organization and Branch for data backfill.

All existing domain rows will be backfilled to this default org.
"""

from django.db import migrations


def create_default_org(apps, schema_editor):
    """Create a default Organization with a Branch so every backfilled row
    has a valid parent."""
    Organization = apps.get_model('core', 'Organization')
    Branch = apps.get_model('core', 'Branch')

    org, _ = Organization.objects.get_or_create(
        name='Default Org',
        defaults={
            'tax_id': 'DEFAULT',
            'is_active': True,
            'settings': {},
        },
    )

    Branch.objects.get_or_create(
        organization=org,
        name='Default Branch',
        defaults={
            'address': 'Auto-created for backfill',
            'is_active': True,
        },
    )


def remove_default_org(apps, schema_editor):
    """Reverse: delete the auto-created default org (only safe when backfill
    has been reversed and no rows reference it)."""
    Organization = apps.get_model('core', 'Organization')
    Organization.objects.filter(name='Default Org', tax_id='DEFAULT').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_organization_organizationmembership_and_more'),
    ]

    operations = [
        migrations.RunPython(create_default_org, remove_default_org),
    ]
