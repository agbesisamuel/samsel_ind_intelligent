"""Preserve response scope, incident identity and immutable encrypted attachment metadata."""

from django.db import migrations

SQL = """
ALTER TABLE incidents_evidenceattachment ADD CONSTRAINT attachment_site_fk
 FOREIGN KEY(site_id,organisation_id) REFERENCES tenants_site(id,organisation_id);
ALTER TABLE incidents_evidenceattachment ADD CONSTRAINT attachment_incident_fk
 FOREIGN KEY(incident_id,organisation_id,site_id) REFERENCES incidents_incident(id,organisation_id,site_id);
CREATE TRIGGER attachment_immutable BEFORE UPDATE OR DELETE ON incidents_evidenceattachment
 FOR EACH ROW EXECUTE FUNCTION sii_audit_immutable();
CREATE TRIGGER incident_identity_fixed BEFORE UPDATE ON incidents_incident
 FOR EACH ROW EXECUTE FUNCTION sii_notification_fixed('sensor_id','gateway_id','rule_version_id','kind','opened_at','synthetic');
ALTER TABLE incidents_incident ADD CONSTRAINT incident_human_status
 CHECK (status IN ('open','acknowledged','investigating','awaiting_qa','qa_reviewed','closed'));
"""


class Migration(migrations.Migration):
    """Install explicit database guards after generated response fields and storage metadata."""

    dependencies = [("incidents", "0003_incident_acknowledged_at_incident_assigned_to_and_more"),
                    ("notifications", "0002_scope_guards")]
    operations = [migrations.RunSQL(SQL, """
ALTER TABLE incidents_incident DROP CONSTRAINT incident_human_status;
DROP TRIGGER incident_identity_fixed ON incidents_incident;
DROP TRIGGER attachment_immutable ON incidents_evidenceattachment;
ALTER TABLE incidents_evidenceattachment DROP CONSTRAINT attachment_incident_fk;
ALTER TABLE incidents_evidenceattachment DROP CONSTRAINT attachment_site_fk;
""")]
