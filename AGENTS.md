# Repository guidance

Read the entire master implementation specification and docs/IMPLEMENTATION_STATUS.md before work. Implement one explicitly authorized sprint at a time. Stop after Sprint 01 until the user authorizes continuation.

Document every new/modified module, class and function with purpose, invariants, side effects and failure behavior where relevant. Document tests by protected behavior. Review documentation as part of completion. Generated migrations and API contracts belong to their generators; document regeneration instead of hand-editing.

Never connect real equipment, send live alerts, introduce customer data, deploy or incur paid services without separate explicit approval. Never implement OT writes or imply food safety from absent alarms. No universal safe temperatures. Enforce tenant/site access on the server when those domains are introduced. Keep secrets out of source and logs.

Use python scripts/dev.py (or equivalent Make targets) for local setup/checks. Preserve source documents. Record exact commands/results and unrun checks honestly.
