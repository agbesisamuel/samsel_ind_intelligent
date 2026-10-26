"""Protect support approval anchors and append-only access logs against raw/bulk writes."""

from django.db import migrations

FORWARD = """
ALTER TABLE support_supportsession ADD CONSTRAINT support_session_site_fk
 FOREIGN KEY (site_id,organisation_id) REFERENCES tenants_site(id,organisation_id);
ALTER TABLE support_supportaccesslog ADD CONSTRAINT support_log_site_fk
 FOREIGN KEY (site_id,organisation_id) REFERENCES tenants_site(id,organisation_id);
ALTER TABLE support_supportaccesslog ADD CONSTRAINT support_log_session_fk
 FOREIGN KEY (session_id,organisation_id,site_id)
 REFERENCES support_supportsession(id,organisation_id,site_id);
CREATE TRIGGER support_scope BEFORE UPDATE ON support_supportsession
 FOR EACH ROW EXECUTE FUNCTION sii_asset_scope_fixed();
CREATE TRIGGER support_anchors BEFORE UPDATE ON support_supportsession
 FOR EACH ROW EXECUTE FUNCTION sii_notification_fixed(
 'supporter_id','approved_by_id','reason','scope','created_at','expires_at');
CREATE TRIGGER support_log_immutable BEFORE UPDATE OR DELETE ON support_supportaccesslog
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
"""
REVERSE = """
DROP TRIGGER support_log_immutable ON support_supportaccesslog;
DROP TRIGGER support_anchors ON support_supportsession;
DROP TRIGGER support_scope ON support_supportsession;
ALTER TABLE support_supportaccesslog DROP CONSTRAINT support_log_session_fk;
ALTER TABLE support_supportaccesslog DROP CONSTRAINT support_log_site_fk;
ALTER TABLE support_supportsession DROP CONSTRAINT support_session_site_fk;
"""


class Migration(migrations.Migration):
    """Retain evidence; rollback requires explicit review of populated grants."""
    dependencies = [("support", "0001_initial"), ("notifications", "0002_scope_guards")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
