"""Keep customer support text, actor/time and exact scope immutable across raw/bulk writes."""

from django.db import migrations

FORWARD = """
ALTER TABLE support_supportticket ADD CONSTRAINT ticket_site_scope
 FOREIGN KEY (site_id,organisation_id) REFERENCES tenants_site(id,organisation_id);
ALTER TABLE support_ticketevent ADD CONSTRAINT ticket_event_site_scope
 FOREIGN KEY (site_id,organisation_id) REFERENCES tenants_site(id,organisation_id);
ALTER TABLE support_ticketevent ADD CONSTRAINT ticket_event_parent_scope
 FOREIGN KEY (ticket_id,organisation_id,site_id)
 REFERENCES support_supportticket(id,organisation_id,site_id);
CREATE TRIGGER ticket_scope_fixed BEFORE UPDATE ON support_supportticket
 FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
CREATE TRIGGER ticket_original_fixed BEFORE UPDATE ON support_supportticket
 FOR EACH ROW EXECUTE FUNCTION sii_notification_fixed(
 'request_id','subject','body','reported_by_id','created_at','synthetic');
CREATE TRIGGER ticket_no_delete BEFORE DELETE ON support_supportticket
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
CREATE TRIGGER ticket_event_immutable BEFORE UPDATE OR DELETE ON support_ticketevent
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
"""
REVERSE = """
DROP TRIGGER ticket_event_immutable ON support_ticketevent;
DROP TRIGGER ticket_no_delete ON support_supportticket;
DROP TRIGGER ticket_original_fixed ON support_supportticket;
DROP TRIGGER ticket_scope_fixed ON support_supportticket;
ALTER TABLE support_ticketevent DROP CONSTRAINT ticket_event_parent_scope;
ALTER TABLE support_ticketevent DROP CONSTRAINT ticket_event_site_scope;
ALTER TABLE support_supportticket DROP CONSTRAINT ticket_site_scope;
"""


class Migration(migrations.Migration):
    """Reverse only after explicit history/retention review; application rollbacks keep these guards."""

    dependencies = [("support", "0003_supportticket_ticketevent_and_more")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
