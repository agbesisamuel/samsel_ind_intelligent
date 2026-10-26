"""Seed local templates and enforce expansion quotas for every SQL/ORM writer.

The subscription lock serializes inventory expansion per organisation. VOLATILE
trigger queries observe committed capacity after a waiting lock is acquired.
Neither expiry nor downgrade touches existing readings, credentials or monitoring.
These are synthetic technical allocations, not customer commercial agreements.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def seed(apps, schema_editor):
    """Bootstrap immutable local catalog and existing tenant allocations without invented sign-off."""
    plan = apps.get_model("billing", "Plan")
    subscription = apps.get_model("billing", "Subscription")
    organisation = apps.get_model("tenants", "Organisation")
    for code, name, sites, sensors, per_site in [
        ("local-trial-v1", "Trial configuration", 2, 80, 40),
        ("local-pilot-v1", "Pilot configuration", 20, 800, 40),
        ("local-demo-v1", "Synthetic developer", 100, 10000, 1000),
    ]:
        plan.objects.create(code=code, name=name, max_sites=sites, max_sensors=sensors,
                            max_sensors_per_site=per_site,
                            features=["manual_invoice_export", "evidence_reports", "support_requests"])
    now = timezone.now()
    subscription.objects.bulk_create([
        subscription(organisation_id=org.pk,
            plan_id="local-demo-v1" if org.is_demo else "local-trial-v1",
            state="active" if org.is_demo else "trial", starts_at=now,
            ends_at=None if org.is_demo else now + timedelta(days=30))
        for org in organisation.objects.all()
    ])


FORWARD = """
CREATE TRIGGER plan_immutable BEFORE UPDATE OR DELETE ON billing_plan
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
CREATE TRIGGER subscription_scope_fixed BEFORE UPDATE ON billing_subscription
 FOR EACH ROW EXECUTE FUNCTION sii_tenant_immutable();
CREATE TRIGGER subscription_start_fixed BEFORE UPDATE ON billing_subscription
 FOR EACH ROW EXECUTE FUNCTION sii_notification_fixed('starts_at','synthetic');
CREATE TRIGGER subscription_no_delete BEFORE DELETE ON billing_subscription
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
CREATE TRIGGER subscription_history_immutable BEFORE UPDATE OR DELETE ON billing_subscriptionchange
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
CREATE TRIGGER invoice_immutable BEFORE UPDATE OR DELETE ON billing_invoicedraft
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
ALTER TABLE billing_subscriptionchange ADD CONSTRAINT subscription_history_scope
 FOREIGN KEY (subscription_id,organisation_id) REFERENCES billing_subscription(id,organisation_id);

CREATE FUNCTION sii_local_subscription_default() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO billing_subscription
 (id,organisation_id,plan_id,state,starts_at,ends_at,billing_name,billing_email,purchase_reference,synthetic)
 VALUES(gen_random_uuid(),NEW.id,
 CASE WHEN NEW.is_demo THEN 'local-demo-v1' ELSE 'local-trial-v1' END,
 CASE WHEN NEW.is_demo THEN 'active' ELSE 'trial' END,
 CURRENT_TIMESTAMP,CASE WHEN NEW.is_demo THEN NULL ELSE CURRENT_TIMESTAMP+interval '30 days' END,
 '','','',TRUE);
 RETURN NEW;
END $$;
CREATE TRIGGER organisation_local_subscription AFTER INSERT ON tenants_organisation
 FOR EACH ROW EXECUTE FUNCTION sii_local_subscription_default();

CREATE FUNCTION sii_expansion_capacity() RETURNS trigger LANGUAGE plpgsql VOLATILE AS $$
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
    (allocation.ends_at IS NOT NULL AND allocation.ends_at<=CURRENT_TIMESTAMP) THEN
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
CREATE TRIGGER site_expansion_quota BEFORE INSERT OR UPDATE ON tenants_site
 FOR EACH ROW EXECUTE FUNCTION sii_expansion_capacity();
CREATE TRIGGER sensor_expansion_quota BEFORE INSERT OR UPDATE ON assets_sensor
 FOR EACH ROW EXECUTE FUNCTION sii_expansion_capacity();
"""
REVERSE = """
DROP TRIGGER sensor_expansion_quota ON assets_sensor;
DROP TRIGGER site_expansion_quota ON tenants_site;
DROP FUNCTION sii_expansion_capacity();
DROP TRIGGER organisation_local_subscription ON tenants_organisation;
DROP FUNCTION sii_local_subscription_default();
ALTER TABLE billing_subscriptionchange DROP CONSTRAINT subscription_history_scope;
DROP TRIGGER invoice_immutable ON billing_invoicedraft;
DROP TRIGGER subscription_history_immutable ON billing_subscriptionchange;
DROP TRIGGER subscription_no_delete ON billing_subscription;
DROP TRIGGER subscription_start_fixed ON billing_subscription;
DROP TRIGGER subscription_scope_fixed ON billing_subscription;
DROP TRIGGER plan_immutable ON billing_plan;
"""


class Migration(migrations.Migration):
    """Preserve initial allocations on reverse; schema reversal destroys retained finance history."""

    dependencies = [("billing", "0001_initial"), ("notifications", "0002_scope_guards"),
                    ("assets", "0004_sensor_capability_reference_sensor_engineering_max_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop), migrations.RunSQL(FORWARD, REVERSE)]
