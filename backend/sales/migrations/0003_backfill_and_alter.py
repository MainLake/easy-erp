# Generated manually for multi-org-rbac Phase 3.
"""Backfill sales rows to default org then make org FK NOT NULL."""

import django.db.models.deletion
from django.db import migrations, models


def backfill_sales(apps, schema_editor):
    org = apps.get_model('core', 'Organization').objects.filter(
        name='Default Org', tax_id='DEFAULT',
    ).first()
    if org is None:
        return

    apps.get_model('sales', 'Customer').objects.filter(
        organization__isnull=True,
    ).update(organization=org)

    apps.get_model('sales', 'SalesOrder').objects.filter(
        organization__isnull=True,
    ).update(organization=org)


def reverse_backfill(apps, schema_editor):
    apps.get_model('sales', 'Customer').objects.all().update(organization=None)
    apps.get_model('sales', 'SalesOrder').objects.all().update(organization=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_create_default_org'),
        ('sales', '0002_customer_organization_salesorder_organization_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_sales, reverse_backfill),

        migrations.AlterField(
            model_name='customer',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sales_customers',
                to='core.organization',
            ),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sales_orders',
                to='core.organization',
            ),
        ),
    ]
