"""Require exact current response grants when assigning through ORM, bulk or raw SQL."""

from django.db import migrations

SQL = """
CREATE FUNCTION sii_incident_assignee() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.assigned_to_id IS NOT NULL AND
    (TG_OP='INSERT' OR NEW.assigned_to_id IS DISTINCT FROM OLD.assigned_to_id) THEN
  IF NOT EXISTS (
   SELECT 1 FROM tenants_roleassignment r JOIN tenants_membership m ON m.id=r.membership_id
   JOIN accounts_customuser u ON u.id=m.user_id
   WHERE m.user_id=NEW.assigned_to_id AND m.organisation_id=NEW.organisation_id
    AND m.active AND u.is_active AND u.verified_at IS NOT NULL
    AND (r.role='owner' OR (r.site_id=NEW.site_id AND r.role IN ('site_admin','qa','operations','operator')))
  ) THEN RAISE EXCEPTION 'Assignee outside response scope' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER incident_assignee_scope BEFORE INSERT OR UPDATE ON incidents_incident
 FOR EACH ROW EXECUTE FUNCTION sii_incident_assignee();
ALTER TABLE incidents_incident ADD CONSTRAINT incident_closed_timestamp
 CHECK ((status='closed') = (closed_at IS NOT NULL));
"""


class Migration(migrations.Migration):
    """Preserve existing assignments as history after revocation; reassignments need current grants."""

    dependencies = [("incidents", "0004_response_guards")]
    operations = [migrations.RunSQL(SQL, """
ALTER TABLE incidents_incident DROP CONSTRAINT incident_closed_timestamp;
DROP TRIGGER incident_assignee_scope ON incidents_incident;
DROP FUNCTION sii_incident_assignee();
""")]
