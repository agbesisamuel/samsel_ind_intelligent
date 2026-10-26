"""Explicit PostgreSQL bulk-write guards for inventory scope and append-only evidence.

Model changes are generated separately. This migration owns the hand-maintained
triple-key foreign keys and triggers. Database-owner bypass is outside this guard.
"""

from django.db import migrations

TABLES = ["building", "zone", "gateway", "sensor", "calibrationrecord",
          "sensorcommissioning", "sitecommissioning", "commissioningtest",
          "commissioningacceptance"]
EVIDENCE = TABLES[4:]
RELATIONS = [("zone", "building", "building"), ("sensor", "zone", "zone"),
             ("sensor", "gateway", "gateway"), ("calibrationrecord", "sensor", "sensor"),
             ("sensorcommissioning", "sensor", "sensor"),
             ("commissioningtest", "commissioning", "sitecommissioning"),
             ("commissioningacceptance", "commissioning", "sitecommissioning")]

FORWARD = """
CREATE FUNCTION sii_asset_scope_fixed() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE field text;
BEGIN
  FOREACH field IN ARRAY ARRAY['organisation_id','site_id','building_id','zone_id',
                              'gateway_id','sensor_id','commissioning_id','external_id'] LOOP
    IF to_jsonb(NEW)->field IS DISTINCT FROM to_jsonb(OLD)->field THEN
      RAISE EXCEPTION 'inventory identity is immutable' USING ERRCODE = '23514';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;
"""
REVERSE = ""
for name in TABLES:
    table = "assets_" + name
    FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {name}_site_tenant_fk
  FOREIGN KEY (site_id, organisation_id) REFERENCES tenants_site(id, organisation_id);
CREATE TRIGGER inventory_scope_fixed BEFORE UPDATE ON {table}
  FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
"""
    REVERSE += f"DROP TRIGGER inventory_scope_fixed ON {table};\n"
    REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {name}_site_tenant_fk;\n"
for source, field, target in RELATIONS:
    constraint = source + "_" + field + "_scope_fk"
    FORWARD += f"""
ALTER TABLE assets_{source} ADD CONSTRAINT {constraint}
  FOREIGN KEY ({field}_id, organisation_id, site_id)
  REFERENCES assets_{target}(id, organisation_id, site_id);
"""
    REVERSE += f"ALTER TABLE assets_{source} DROP CONSTRAINT {constraint};\n"
for name in EVIDENCE:
    FORWARD += f"""
CREATE TRIGGER evidence_append_only BEFORE UPDATE OR DELETE ON assets_{name}
  FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
"""
    REVERSE += f"DROP TRIGGER evidence_append_only ON assets_{name};\n"
REVERSE += "DROP FUNCTION sii_asset_scope_fixed();"


class Migration(migrations.Migration):
    """Install exact-site foreign keys after generated schemas and shared audit guards exist."""

    dependencies = [("assets", "0001_initial"), ("tenants", "0002_scope_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
