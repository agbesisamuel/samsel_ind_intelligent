"""Check expansion expiry against wall time after locks, including long-running transactions."""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION sii_expansion_capacity() RETURNS trigger LANGUAGE plpgsql VOLATILE AS $$
DECLARE allocation record; used bigint; local_used bigint;
BEGIN
 IF TG_TABLE_NAME='tenants_site' THEN
   IF NEW.archived THEN RETURN NEW; END IF;
   IF TG_OP='UPDATE' AND NOT OLD.archived THEN RETURN NEW; END IF;
 ELSE
   IF NEW.state='retired' THEN RETURN NEW; END IF;
   IF TG_OP='UPDATE' AND OLD.state<>'retired' THEN RETURN NEW; END IF;
 END IF;
 SELECT s.state,s.ends_at,p.max_sites,p.max_sensors,p.max_sensors_per_site
 INTO allocation FROM billing_subscription s JOIN billing_plan p ON p.code=s.plan_id
 WHERE s.organisation_id=NEW.organisation_id FOR UPDATE OF s;
 IF NOT FOUND THEN
   RAISE EXCEPTION 'local plan configuration required' USING ERRCODE='23514';
 END IF;
 IF allocation.state NOT IN ('trial','pilot','active','ending') OR
    (allocation.ends_at IS NOT NULL AND allocation.ends_at<=clock_timestamp()) THEN
   RAISE EXCEPTION 'commercial expansion blocked; existing monitoring retained' USING ERRCODE='23514';
 END IF;
 IF TG_TABLE_NAME='tenants_site' THEN
   SELECT count(*) INTO used FROM tenants_site
    WHERE organisation_id=NEW.organisation_id AND NOT archived AND id<>NEW.id;
   IF used>=allocation.max_sites THEN
     RAISE EXCEPTION 'site capacity reached' USING ERRCODE='23514';
   END IF;
 ELSE
   SELECT count(*) INTO used FROM assets_sensor
    WHERE organisation_id=NEW.organisation_id AND state<>'retired' AND id<>NEW.id;
   SELECT count(*) INTO local_used FROM assets_sensor
    WHERE organisation_id=NEW.organisation_id AND site_id=NEW.site_id
      AND state<>'retired' AND id<>NEW.id;
   IF used>=allocation.max_sensors OR local_used>=allocation.max_sensors_per_site THEN
     RAISE EXCEPTION 'sensor capacity reached' USING ERRCODE='23514';
   END IF;
 END IF;
 RETURN NEW;
END $$;
"""
REVERSE = FORWARD.replace("clock_timestamp()", "CURRENT_TIMESTAMP")


class Migration(migrations.Migration):
    """Keep all quota/scope guards; change only the expiry clock used after row locking."""

    dependencies = [("billing", "0002_local_plans_and_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
