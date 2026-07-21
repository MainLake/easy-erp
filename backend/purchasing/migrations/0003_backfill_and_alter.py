# Generated manually for multi-org-rbac Phase 3.
"""Backfill purchasing rows to default org then make org FK NOT NULL."""

import django.db.models.deletion
from django.db import migrations, models


def backfill_purchasing(apps, schema_editor):
    org = apps.get_model('core', 'Organization').objects.filter(
        name='Default Org', tax_id='DEFAULT',
    ).first()
    if org is None:
        return

    apps.get_model('purchasing', 'Supplier').objects.filter(
        organization__isnull=True,
    ).update(organization=org)

    apps.get_model('purchasing', 'PurchaseOrder').objects.filter(
        organization__isnull=True,
    ).update(organization=org)


def reverse_backfill(apps, schema_editor):
    apps.get_model('purchasing', 'Supplier').objects.all().update(organization=None)
    apps.get_model('purchasing', 'PurchaseOrder').objects.all().update(organization=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_create_default_org'),
        ('purchasing', '0002_purchaseorder_organization_supplier_organization_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_purchasing, reverse_backfill),

        migrations.AlterField(
            model_name='supplier',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='purchasing_suppliers',
                to='core.organization',
            ),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='purchasing_orders',
                to='core.organization',
            ),
        ),
    ]
