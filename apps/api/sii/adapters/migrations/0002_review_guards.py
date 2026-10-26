"""Protect synthetic pilot history and exact site ownership against raw/bulk writes."""

from django.db import migrations

FORWARD = """
ALTER TABLE adapters_pilotreview ADD CONSTRAINT pilot_review_site_fk
 FOREIGN KEY (site_id,organisation_id) REFERENCES tenants_site(id,organisation_id);
CREATE TRIGGER pilot_review_immutable BEFORE UPDATE OR DELETE ON adapters_pilotreview
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
"""
REVERSE = """
DROP TRIGGER pilot_review_immutable ON adapters_pilotreview;
ALTER TABLE adapters_pilotreview DROP CONSTRAINT pilot_review_site_fk;
"""


class Migration(migrations.Migration):
    """Rollback removes evidence protection; never reverse against retained customer history."""

    dependencies = [("adapters", "0001_initial"), ("tenants", "0002_scope_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
