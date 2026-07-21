# Generated manually for multi-org-rbac Phase 3.
"""Backfill invoicing orgs, invoice core_org, and note org FKs then make NOT NULL."""

import django.db.models.deletion
from django.db import migrations, models


def backfill_invoicing(apps, schema_editor):
    core_org = apps.get_model('core', 'Organization').objects.filter(
        name='Default Org', tax_id='DEFAULT',
    ).first()
    if core_org is None:
        return

    InvoicingOrg = apps.get_model('invoicing', 'Organization')
    Invoice = apps.get_model('invoicing', 'Invoice')
    CreditDebitNote = apps.get_model('invoicing', 'CreditDebitNote')

    # --- 1. Backfill invoicing Organization rows ---
    for inv_org in InvoicingOrg.objects.filter(core_organization__isnull=True):
        inv_org.core_organization = core_org
        inv_org.save()

    # If no invoicing org exists yet, create one for the default core org.
    if not InvoicingOrg.objects.exists():
        InvoicingOrg.objects.create(
            name='Default Org',
            tax_id='DEFAULT',
            core_organization=core_org,
        )

    # --- 2. Backfill Invoice.core_organization via invoice.organization chain ---
    for invoice in Invoice.objects.filter(core_organization__isnull=True):
        inv_org = invoice.organization  # invoicing.Organization FK
        if inv_org is not None and inv_org.core_organization_id is not None:
            invoice.core_organization_id = inv_org.core_organization_id
            invoice.save()
        elif inv_org is None:
            # Invoice has no invoicing org — assign to default core org.
            invoice.core_organization = core_org
            invoice.save()

    # --- 3. Backfill CreditDebitNote.organization via invoice chain ---
    for note in CreditDebitNote.objects.filter(organization__isnull=True):
        if note.invoice is not None and note.invoice.core_organization_id is not None:
            note.organization_id = note.invoice.core_organization_id
            note.save()


def reverse_backfill(apps, schema_editor):
    apps.get_model('invoicing', 'Organization').objects.all().update(
        core_organization=None,
    )
    apps.get_model('invoicing', 'Invoice').objects.all().update(
        core_organization=None,
    )
    apps.get_model('invoicing', 'CreditDebitNote').objects.all().update(
        organization=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_create_default_org'),
        ('invoicing', '0002_add_core_org_and_fks'),
    ]

    operations = [
        migrations.RunPython(backfill_invoicing, reverse_backfill),

        # --- Make invoicing Organization.core_organization NOT NULL ---
        migrations.AlterField(
            model_name='organization',
            name='core_organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='invoicing_orgs',
                to='core.organization',
            ),
        ),

        # --- Make Invoice.core_organization NOT NULL ---
        migrations.AlterField(
            model_name='invoice',
            name='core_organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='invoicing_invoices',
                to='core.organization',
            ),
        ),

        # --- Make CreditDebitNote.organization NOT NULL ---
        migrations.AlterField(
            model_name='creditdebitnote',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='invoicing_credit_debit_notes',
                to='core.organization',
            ),
        ),
    ]
