"""Guard rejection event scope and enqueue historical local rejections without altering evidence."""

from django.db import migrations


def backfill(apps, schema_editor):
    """Give pre-envelope rejections a durable processing reference; source records remain untouched."""
    rejection = apps.get_model("telemetry", "Rejection")
    outbox = apps.get_model("telemetry", "ProcessingOutbox")
    for item in rejection.objects.filter(processingoutbox__isnull=True).iterator(chunk_size=100):
        outbox.objects.create(organisation_id=item.organisation_id, site_id=item.site_id,
                              rejection_id=item.pk, available_at=item.received_at)


class Migration(migrations.Migration):
    """Install exact related scope and preserve all queued rejection event records on rollback."""

    dependencies = [("telemetry", "0004_processingoutbox_rejection_and_more")]
    operations = [migrations.RunSQL("""
        ALTER TABLE telemetry_processingoutbox ADD CONSTRAINT outbox_rejection_scope_fk
        FOREIGN KEY (rejection_id, organisation_id, site_id)
        REFERENCES telemetry_rejection(id, organisation_id, site_id);
        """, "ALTER TABLE telemetry_processingoutbox DROP CONSTRAINT outbox_rejection_scope_fk;"),
        migrations.RunPython(backfill, migrations.RunPython.noop)]
