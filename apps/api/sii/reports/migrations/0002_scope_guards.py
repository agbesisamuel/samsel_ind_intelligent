"""Protect report tenant anchors and immutable requests/snapshots even through raw SQL."""

from django.db import migrations

RELATIONS = {
    "reportjob": [("zone", "assets_zone")],
    "reportsnapshot": [("job", "reports_reportjob")],
    "reportevent": [("job", "reports_reportjob")],
    "downloadgrant": [("job", "reports_reportjob")],
}
FIXED = {
    "reportjob": ["zone_id", "start", "end", "format", "locale", "requested_by_id",
                  "requested_at", "expires_at", "configuration"],
    "downloadgrant": ["job_id", "user_id", "expires_at"],
}
FORWARD, REVERSE = "", ""
for short, relations in RELATIONS.items():
    table = "reports_" + short
    FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {table}_site_fk FOREIGN KEY (site_id,organisation_id)
 REFERENCES tenants_site(id,organisation_id);
CREATE TRIGGER report_scope BEFORE UPDATE ON {table}
 FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
"""
    REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {table}_site_fk; DROP TRIGGER report_scope ON {table};\n"
    for field, target in relations:
        FORWARD += f"ALTER TABLE {table} ADD CONSTRAINT {table}_{field}_fk FOREIGN KEY ({field}_id,organisation_id,site_id) REFERENCES {target}(id,organisation_id,site_id);\n"
        REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {table}_{field}_fk;\n"
    if short in ["reportsnapshot", "reportevent"]:
        FORWARD += f"CREATE TRIGGER report_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();\n"
        REVERSE += f"DROP TRIGGER report_immutable ON {table};\n"
    if short in FIXED:
        fields = ",".join("'" + field + "'" for field in FIXED[short])
        FORWARD += f"CREATE TRIGGER report_anchors BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION sii_notification_fixed({fields});\n"
        REVERSE += f"DROP TRIGGER report_anchors ON {table};\n"


class Migration(migrations.Migration):
    """Apply explicit guards after generated schema; never discard populated evidence."""

    dependencies = [("reports", "0001_initial"), ("notifications", "0002_scope_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
