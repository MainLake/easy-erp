# Generated manually for multi-org-rbac Phase 3.
"""Backfill inventory rows to default org then make org FK NOT NULL."""

import django.db.models.deletion
from django.db import migrations, models


def backfill_inventory(apps, schema_editor):
    org = apps.get_model('core', 'Organization').objects.filter(
        name='Default Org', tax_id='DEFAULT',
    ).first()
    if org is None:
        return  # should not happen — 0003_create_default_org runs first

    apps.get_model('inventory', 'Category').objects.filter(
        organization__isnull=True,
    ).update(organization=org)

    apps.get_model('inventory', 'Product').objects.filter(
        organization__isnull=True,
    ).update(organization=org)

    apps.get_model('inventory', 'Warehouse').objects.filter(
        organization__isnull=True,
    ).update(organization=org)


def reverse_backfill(apps, schema_editor):
    apps.get_model('inventory', 'Category').objects.all().update(organization=None)
    apps.get_model('inventory', 'Product').objects.all().update(organization=None)
    apps.get_model('inventory', 'Warehouse').objects.all().update(organization=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_create_default_org'),
        ('inventory', '0003_category_organization_product_organization_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_inventory, reverse_backfill),

        # AlterField: null=True → null=False on all three inventory models.
        migrations.AlterField(
            model_name='category',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_categories',
                to='core.organization',
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_products',
                to='core.organization',
            ),
        ),
        migrations.AlterField(
            model_name='warehouse',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_warehouses',
                to='core.organization',
            ),
        ),

        # Per-org SKU uniqueness (spec I1).
        migrations.AlterUniqueTogether(
            name='product',
            unique_together={('sku', 'organization')},
        ),
    ]
