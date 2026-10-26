"""Validate polymorphic immutable event sources and envelope ownership at the DB boundary."""

from django.db import migrations

FORWARD = """
ALTER TABLE events_domainevent ADD CONSTRAINT domain_site_fk FOREIGN KEY (site_id,organisation_id)
 REFERENCES tenants_site(id,organisation_id);
CREATE FUNCTION sii_domain_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_table text; present boolean;
BEGIN
 source_table := CASE NEW.source_model
  WHEN 'incident' THEN 'incidents_incidentevent'
  WHEN 'freshness' THEN 'monitoring_freshnessevent'
  WHEN 'notification' THEN 'notifications_notificationattempt'
  WHEN 'report' THEN 'reports_reportevent' ELSE NULL END;
 IF source_table IS NULL THEN RAISE EXCEPTION 'Unknown domain source' USING ERRCODE='23514'; END IF;
 EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I WHERE id=$1 AND organisation_id=$2 AND site_id=$3)',source_table)
 INTO present USING NEW.source_id,NEW.organisation_id,NEW.site_id;
 IF NOT present OR NEW.envelope->>'organisation_id' IS DISTINCT FROM NEW.organisation_id::text
 OR NEW.envelope->>'site_id' IS DISTINCT FROM NEW.site_id::text
 OR NEW.envelope->>'event_id' IS DISTINCT FROM NEW.id::text
 OR NEW.envelope->>'event_type' IS DISTINCT FROM NEW.event_type THEN
  RAISE EXCEPTION 'Domain envelope scope mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER domain_source BEFORE INSERT ON events_domainevent
 FOR EACH ROW EXECUTE FUNCTION sii_domain_source();
CREATE TRIGGER domain_scope BEFORE UPDATE ON events_domainevent
 FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
CREATE TRIGGER domain_fixed BEFORE UPDATE ON events_domainevent
 FOR EACH ROW EXECUTE FUNCTION sii_notification_fixed('source_model','source_id','event_type','envelope');
"""
REVERSE = """
DROP TRIGGER domain_fixed ON events_domainevent;
DROP TRIGGER domain_scope ON events_domainevent;
DROP TRIGGER domain_source ON events_domainevent;
DROP FUNCTION sii_domain_source();
ALTER TABLE events_domainevent DROP CONSTRAINT domain_site_fk;
"""


class Migration(migrations.Migration):
    """Keep raw/bulk source references within exact tenant/site and immutable after insertion."""
    dependencies = [("events", "0001_initial"), ("notifications", "0002_scope_guards"),
                    ("reports", "0002_scope_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
