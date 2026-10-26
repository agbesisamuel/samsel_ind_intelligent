"""Hand-authored PostgreSQL guards supplement generated schema for non-ORM writers.

Regenerate model changes with makemigrations, but maintain these explicit SQL
constraints/triggers here. Reversal removes guards only, not customer data.
Database owners can bypass triggers; production role separation/anchoring is later work.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION sii_tenant_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.organisation_id IS DISTINCT FROM OLD.organisation_id THEN
    RAISE EXCEPTION 'tenant ownership is immutable' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION sii_membership_identity_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN
    RAISE EXCEPTION 'membership identity is immutable' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION sii_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit evidence is append only' USING ERRCODE = '23514';
END $$;
ALTER TABLE tenants_roleassignment ADD CONSTRAINT role_membership_tenant_fk
  FOREIGN KEY (membership_id, organisation_id) REFERENCES tenants_membership(id, organisation_id);
ALTER TABLE tenants_roleassignment ADD CONSTRAINT role_site_tenant_fk
  FOREIGN KEY (site_id, organisation_id) REFERENCES tenants_site(id, organisation_id);
ALTER TABLE tenants_invitation ADD CONSTRAINT invitation_site_tenant_fk
  FOREIGN KEY (site_id, organisation_id) REFERENCES tenants_site(id, organisation_id);
ALTER TABLE audit_auditevent ADD CONSTRAINT audit_site_tenant_fk
  FOREIGN KEY (site_id, organisation_id) REFERENCES tenants_site(id, organisation_id);
ALTER TABLE audit_auditevent ADD CONSTRAINT audit_site_needs_tenant
  CHECK (site_id IS NULL OR organisation_id IS NOT NULL);
CREATE TRIGGER membership_identity BEFORE UPDATE ON tenants_membership
  FOR EACH ROW EXECUTE FUNCTION sii_membership_identity_immutable();
CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit_auditevent
  FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
"""
REVERSE = """
DROP TRIGGER audit_no_mutation ON audit_auditevent;
DROP TRIGGER membership_identity ON tenants_membership;
ALTER TABLE audit_auditevent DROP CONSTRAINT audit_site_needs_tenant;
ALTER TABLE audit_auditevent DROP CONSTRAINT audit_site_tenant_fk;
ALTER TABLE tenants_invitation DROP CONSTRAINT invitation_site_tenant_fk;
ALTER TABLE tenants_roleassignment DROP CONSTRAINT role_site_tenant_fk;
ALTER TABLE tenants_roleassignment DROP CONSTRAINT role_membership_tenant_fk;
DROP FUNCTION sii_audit_immutable();
DROP FUNCTION sii_membership_identity_immutable();
"""
TABLES = ["tenants_site", "tenants_membership", "tenants_roleassignment", "tenants_invitation"]
for table in TABLES:
    FORWARD += f"CREATE TRIGGER tenant_fixed BEFORE UPDATE ON {table} " \
               "FOR EACH ROW EXECUTE FUNCTION sii_tenant_immutable();\n"
    REVERSE += f"DROP TRIGGER tenant_fixed ON {table};\n"
REVERSE += "DROP FUNCTION sii_tenant_immutable();"


class Migration(migrations.Migration):
    """Apply tenant ownership and append-only evidence guards after all referenced tables exist."""

    dependencies = [("tenants", "0001_initial"), ("audit", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
