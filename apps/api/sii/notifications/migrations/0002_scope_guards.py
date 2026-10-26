"""Explicit tenant/site FKs and immutable intent/evidence anchors for notification delivery."""

from django.db import migrations

RELATIONS = {
    "alertcontact": [],
    "alertroute": [("contact", "notifications_alertcontact"), ("contingency", "notifications_alertcontact")],
    "escalationpolicy": [("route", "notifications_alertroute"), ("contact", "notifications_alertcontact")],
    "eventplan": [("event", "incidents_incidentevent")],
    "notification": [("route", "notifications_alertroute"), ("contact", "notifications_alertcontact"), ("event", "incidents_incidentevent")],
    "notificationattempt": [("notification", "notifications_notification")],
    "deliveryissue": [("notification", "notifications_notification"), ("event", "incidents_incidentevent")],
}
FIXED = {
    "alertcontact": ["user_id"],
    "alertroute": ["name", "contact_id", "contingency_id", "kinds", "severity", "timezone", "shift_start", "shift_end", "created_at", "created_by_id"],
    "notification": ["route_id", "contact_id", "event_id", "dedup_key", "level", "envelope", "created_at"],
    "deliveryissue": ["notification_id", "event_id", "reason", "opened_at"],
}
FORWARD = """
CREATE FUNCTION sii_notification_fixed() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE field text;
BEGIN
 FOREACH field IN ARRAY TG_ARGV LOOP
  IF (to_jsonb(OLD)->field) IS DISTINCT FROM (to_jsonb(NEW)->field) THEN
   RAISE EXCEPTION 'Notification evidence anchor is immutable' USING ERRCODE='23514';
  END IF;
 END LOOP;
 RETURN NEW;
END $$;
"""
REVERSE = ""
for short, relations in RELATIONS.items():
    table = "notifications_" + short
    FORWARD += f"""
ALTER TABLE {table} ADD CONSTRAINT {table}_site_fk FOREIGN KEY (site_id,organisation_id)
 REFERENCES tenants_site(id,organisation_id);
CREATE TRIGGER notification_scope BEFORE UPDATE ON {table}
 FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
"""
    REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {table}_site_fk; DROP TRIGGER notification_scope ON {table};\n"
    for field, target in relations:
        FORWARD += f"ALTER TABLE {table} ADD CONSTRAINT {table}_{field}_fk FOREIGN KEY ({field}_id,organisation_id,site_id) REFERENCES {target}(id,organisation_id,site_id);\n"
        REVERSE += f"ALTER TABLE {table} DROP CONSTRAINT {table}_{field}_fk;\n"
    if short in ["escalationpolicy", "eventplan", "notificationattempt"]:
        FORWARD += f"CREATE TRIGGER notification_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();\n"
        REVERSE += f"DROP TRIGGER notification_immutable ON {table};\n"
    if short in FIXED:
        fields = ",".join("'"+field+"'" for field in FIXED[short])
        FORWARD += f"CREATE TRIGGER notification_anchors BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION sii_notification_fixed({fields});\n"
        REVERSE += f"DROP TRIGGER notification_anchors ON {table};\n"
REVERSE += "DROP FUNCTION sii_notification_fixed();"


class Migration(migrations.Migration):
    """Protect raw/bulk paths after the generated schema exists; retain all populated evidence."""

    dependencies = [("notifications", "0001_initial"), ("rules", "0002_evidence_scope_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
