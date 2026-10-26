# Sprint 09 verification - 2026-10-21

Windows/Docker Desktop local synthetic stack; no remote CI or customer deployment.

- Full suites: **142 backend passed in 72.98s**, **13 component passed in 6.35s**.
- Final expanded report suite: **8 passed in 13.94s** (three additional cases;
  **145 unique backend tests** now). Golden redacted CSV, deterministic PDF, DST fold,
  year/ambiguous-window rejection, late-arrival cutoff, operator/foreign scope,
  immutable DB anchors, single-use/expiry, revoked worker, lease/retry/admission.
- Lint: Ruff **113 files**, Django check **0 issues**, migration drift **none**,
  ESLint/Prettier/TypeScript all passed. Documentation review completed.
- Contracts regenerated/validated with **0 warnings**; generated TS retained.
- Build: **12 images**, frontend **86 modules**, JS **390.95 kB / 118.49 kB gzip**,
  CSS **5.69 kB / 1.92 kB gzip**; Vite **4.34s**, TypeScript passed.
- Actual final worker/S3 drill: PDF `344f497f-1a7f-4f63-ad64-cbbcc0c893a5`,
  CSV `e31a1462-8dcd-4ac7-be27-444da8166b19`; encrypted object, no plaintext,
  checksum and scoped single-use download passed. Generated two-page PDF rendered
  with Poppler and both pages inspected; no clipping, preserved record pagination.
  Poppler warned about unused Symbol/ArialUnicode display fonts; visible text intact.
- Chromium E2E **2 passed in 12.1s**, including direct-route operator report denial.
- Python/npm audits: **0 known vulnerabilities**. Gitleaks: **236 files / 1.50 MB**,
  **0 leaks**, ignored local credentials excluded. **14 services healthy**.

Initial PDF test/drill found duplicate `invariant` canvas keyword; corrected and
rerun. Initial TypeScript check found wrong shared Field component interface;
replaced with documented native labelled controls and passed. Final PDF pagination
refinement passed the eight report tests and actual worker drill again. No checks
were weakened. Source datasets are never changed by report generation/download.

Production remains blocked by security/legal/site gates. One-year/high-volume
reports require explicit reduction (31 days / bounded records), never silent sampling.
Report expiry denies access; reviewed local ciphertext cleanup is documented.
