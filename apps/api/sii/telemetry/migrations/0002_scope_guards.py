"""Hand-maintained SQL guards supplement generated models for raw/bulk writes.

Raw observations/rejections are immutable; credential/outbox identity cannot move.
Database-owner bypass remains an explicit infrastructure release boundary.
"""

from django.db import migrations

FORWARD = ""
REVERSE = ""
for name in ["devicecredential", "reading", "rejection", "processingoutbox"]:
    table = "telemetry_" + name
    FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {name}_site_org_fk
 FOREIGN KEY (site_id, organisation_id) REFERENCES tenants_site(id, organisation_id);
CREATE TRIGGER telemetry_scope_fixed BEFORE UPDATE ON {table}
 FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
"""
    REVERSE += f"DROP TRIGGER telemetry_scope_fixed ON {table};\n"
    REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {name}_site_org_fk;\n"
    relations = [("reading", "telemetry_reading")] if name == "processingoutbox" else [("gateway", "assets_gateway")]
    if name == "reading":
        relations += [("sensor", "assets_sensor")]
    for field, target in relations:
        FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {name}_{field}_scope_fk
 FOREIGN KEY ({field}_id, organisation_id, site_id) REFERENCES {target}(id, organisation_id, site_id);
"""
        REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {name}_{field}_scope_fk;\n"
    if name in ["reading", "rejection"]:
        FORWARD += f"""
CREATE TRIGGER telemetry_append_only BEFORE UPDATE OR DELETE ON {table}
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
"""
        REVERSE += f"DROP TRIGGER telemetry_append_only ON {table};\n"


class Migration(migrations.Migration):
    """Install immutable site ownership and exact related-object scope constraints."""

    dependencies = [("telemetry", "0001_initial"), ("assets", "0002_scope_evidence_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
