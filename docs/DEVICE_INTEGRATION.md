# Device integration and credential provisioning

Sprint 03 implements inventory and qualification references only. Supported tested
real gateway/sensor profiles: **none**. Live integration is **BLOCKED:
CUSTOMER/SUPPLIER APPROVAL REQUIRED**. Only qualified explicitly authorized read-only
integrations may be enabled. No PLC/register/setpoint/control writes exist.
Synthetic names and intervals are not vendor compatibility or safety-limit claims.

## One-time credential design (implementation/enforcement in Sprint 04)

Provision a gateway-specific random 256-bit secret only after an authorized
owner/site administrator completes fresh step-up. Bind the public key identifier
immutably to one organisation/site/gateway; permission comes from this binding,
not a client-supplied org or device claim. Return the secret once over the protected
provisioning response, never in list/admin/export/log output. Separate device
credentials from Django human sessions and never accept a device token for tenant
administration. Use secret-manager encryption when HMAC verification needs the
original key; bearer-only alternatives store a verifier hash. Record issuance,
rotation, expiry and revocation with identifiers only.

Rotation creates a new credential version, exposes its secret once, and explicitly
revokes/retires the previous key; no unknown default/shared secret. Revoked/expired
or unqualified/retired gateways and assigned sensors fail closed. Local test keys
are synthetic, generated at runtime and cannot satisfy real partner approval.

HTTPS and MQTT must converge on one typed, versioned event contract with bounded
payloads, timestamp/units/device validation, durable acceptance, deduplication and
replay protection. Use TLS and broker ACLs; deployment authorization is separate.
A publisher-supplied tenant/sensor ID never broadens the credential scope. Preserve
observed/received times and backfill provenance. Do not claim acknowledgment before
durable storage. Simulator, actual transport authentication and replay behavior are
implemented and verified in Sprint 04; see TELEMETRY_PROTOCOL.md. Inventory
registration alone still grants no transport credential or real-device approval.
