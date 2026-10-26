"""Explicit DB scope and immutable evidence guards for rules and incident chronology."""

from django.db import migrations

TABLES = {
 "rules_ruleset": [("zone", "assets_zone")],
 "rules_ruleversion": [("ruleset", "rules_ruleset")],
 "rules_rulebacktest": [("version", "rules_ruleversion")],
 "rules_ruleapproval": [("version", "rules_ruleversion"), ("backtest", "rules_rulebacktest")],
 "rules_ruleactivation": [("ruleset", "rules_ruleset"), ("approval", "rules_ruleapproval")],
 "rules_rulecursor": [("version", "rules_ruleversion"), ("sensor", "assets_sensor")],
 "rules_ruleevaluation": [("version", "rules_ruleversion"), ("reading", "telemetry_reading")],
 "rules_suppressionwindow": [("sensor", "assets_sensor")],
 "incidents_incident": [("sensor", "assets_sensor"), ("gateway", "assets_gateway"), ("rule_version", "rules_ruleversion")],
 "incidents_incidentevent": [("incident", "incidents_incident")],
}
FORWARD, REVERSE = "", ""
for table, relations in TABLES.items():
    FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {table}_site_fk FOREIGN KEY (site_id, organisation_id)
 REFERENCES tenants_site(id, organisation_id);
CREATE TRIGGER rule_scope_fixed BEFORE UPDATE ON {table}
 FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
"""
    REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {table}_site_fk;\nDROP TRIGGER rule_scope_fixed ON {table};\n"
    for field, target in relations:
        FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {table}_{field}_fk
 FOREIGN KEY ({field}_id, organisation_id, site_id) REFERENCES {target}(id, organisation_id, site_id);
"""
        REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {table}_{field}_fk;\n"
    if table not in ["rules_rulecursor", "incidents_incident"]:
        FORWARD += f"CREATE TRIGGER rule_evidence_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();\n"
        REVERSE += f"DROP TRIGGER rule_evidence_immutable ON {table};\n"


class Migration(migrations.Migration):
    """Install guards after generated schema across both dependent apps exists."""

    dependencies = [("rules", "0001_initial"), ("incidents", "0002_initial"),
                    ("telemetry", "0005_rejection_outbox_scope")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
