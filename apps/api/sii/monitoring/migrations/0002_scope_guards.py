"""Explicit DB guards for freshness scope, immutable approval and transition evidence."""

from django.db import migrations

FORWARD, REVERSE = "", ""
for name in ["freshnesspolicy", "sensorstate", "freshnessevent"]:
    table = "monitoring_"+name
    FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {name}_site_org_fk FOREIGN KEY (site_id, organisation_id)
 REFERENCES tenants_site(id, organisation_id);
CREATE TRIGGER monitoring_scope_fixed BEFORE UPDATE ON {table}
 FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
"""
    REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {name}_site_org_fk;\nDROP TRIGGER monitoring_scope_fixed ON {table};\n"
    if name != "freshnesspolicy":
        FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {name}_sensor_scope_fk FOREIGN KEY (sensor_id, organisation_id, site_id)
 REFERENCES assets_sensor(id, organisation_id, site_id);
"""
        REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {name}_sensor_scope_fk;\n"
    if name != "sensorstate":
        FORWARD += f"CREATE TRIGGER monitoring_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();\n"
        REVERSE += f"DROP TRIGGER monitoring_immutable ON {table};\n"
FORWARD += """
ALTER TABLE monitoring_sensorstate ADD CONSTRAINT state_reading_scope_fk
 FOREIGN KEY (reading_id, organisation_id, site_id) REFERENCES telemetry_reading(id, organisation_id, site_id);
"""
REVERSE += "ALTER TABLE monitoring_sensorstate DROP CONSTRAINT state_reading_scope_fk;"


class Migration(migrations.Migration):
    """Protect ordinary/raw bulk writes independently of view permission checks."""

    dependencies = [("monitoring", "0001_initial"), ("telemetry", "0003_reading_gateway_event")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
