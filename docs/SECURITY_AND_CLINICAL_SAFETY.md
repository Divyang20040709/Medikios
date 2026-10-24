# MediKiosk — Security, Clinical Safety & Limitations

> Scope: exactly what the current code does, verified in Phases 6–8 (bcrypt auth path, JWT guards,
> consent enforcement, red-flag independence, sign-off immutability, FHIR honesty).
> **MediKiosk is an academic prototype.** It is **not** a certified medical device, **not** a
> diagnostic system, **not** a production-ready hospital system, and **not** ABDM-certified.

## 1. Authentication & Credentials

| Mechanism | Actual behavior (verified in code) |
|---|---|
| Password hashing | bcrypt via passlib (`requirements.txt` pins `bcrypt<4.1`). New/user-set passwords are always bcrypt-hashed. |
| Legacy SHA-256 migration | Rows hashed with the old unsalted SHA-256 scheme are detected (`is_legacy_hash` — hash does not start with `$2`) and transparently re-hashed with bcrypt on successful login; the upgrade writes a `PASSWORD_HASH_UPGRADED` audit row. Note: legacy unsalted SHA-256 is weak — any account that never logged in since Phase 6 still carries it. |
| Staff login (DOCTOR/ADMIN) | **Password is mandatory** — `POST /api/auth/login` without a password for a staff role returns 401 `Password is required for staff sign-in`. Role in the request must match the user row (otherwise 401). |
| Patient login | Identifier-based and intentionally passwordless: unknown identifiers auto-register `User` + `Patient` + a `QUEUED` encounter. This is a kiosk convenience path, not a strong authentication mechanism. |
| JWT | HS256, `sub` = user id, plus `role`/`name` claims, expiry `ACCESS_TOKEN_EXPIRE_MINUTES` (default 480 = 8 h). **The role claim is re-checked against the database row**, so a stale token cannot escalate privileges beyond the live user record. |
| Dev default secret | `main.py` prints a startup WARNING if `JWT_SECRET` is still the built-in development value. Rotate it per deployment. |

### Known gaps (verified as *not implemented* — do not claim otherwise)
- **No login rate limiting or lockout** — brute force is only slowed by bcrypt itself.
- **No token revocation / logout blocklist** — a leaked JWT is valid until it expires.
- **No patient-to-doctor assignment model** — any authenticated DOCTOR can open any encounter's
  dossier. (Known, accepted limitation for a single-clinic prototype.)
- Kiosk write endpoints (`/api/intake/*`, document upload) remain **anonymous by design** —
  see §3.

## 2. Authorization (RBAC)

- Every PHI read, clinical action and admin view is behind `require_authenticated_roles(...)`
  (`Depends` on a valid Bearer JWT): doctor queue/dossier, summary edit/sign-off, entity
  verification, document listing/download, admin telemetry/audit logs, FHIR export.
- **ADMIN may not sign off** a clinical summary (DOCTOR-only, 403) — separation of administrative
  and clinical authority.
- Anonymous or non-clinical callers on clinical endpoints → 401/403 (tested in
  `backend/tests/test_integration_phase7.py` and Phase 6 tests).
- PHI file downloads serve only through the authenticated
  `GET /api/documents/file/{document_id}` route; the raw `/uploads` StaticFiles mount was removed
  in Phase 6 (filename-UUID obscurity is not treated as access control).
- Residual: the older lenient `require_roles` dependency still exists for kiosk-compatibility
  endpoints; anything handling PHI or clinical decisions uses the strict guard.

## 3. Kiosk Session Boundaries (anonymous writes)

Shared-device intake has no patient login. The boundary is an unguessable **uuid4**
`session_id`/`encounter_id` issued at `/api/intake/init`:
- Answers, consent, follow-ups, uploads and completion all scope to that UUID.
- Cross-encounter consent submission (encounter ↔ patient mismatch) → 400 (enforced + tested).
- Risk accepted for the prototype: anyone who obtains a live UUID could write to that session.
  UUIDs are not logged in URLs beyond audit rows and expire with the session's clinical use.

## 4. Consent

- `/api/intake/init` creates a **PENDING** `ConsentRecord` — `granted=False`, `granted_at=NULL`.
  Nothing is "auto-consented". (Phase 7 fixed a model-level default that used to stamp this.)
- Only `POST /api/intake/consent` with an explicit `granted: true/false` records a decision;
  it is idempotent for repeat same-value calls, and the **first explicit decision is always
  audited** (including a pending → decline, which initially wrote no audit row — fixed Phase 7).
- FHIR export maps reality: pending → `draft` + provision `deny`; declined → `revoked`;
  never an optimistic `active`.
- Declining consent stops data flow: the intake UI does not proceed to questions, and no
  interview data is collected.

## 5. Clinical Safety Guardrails

1. **Red flags are deterministic.** `red_flags.py` pattern rules run on every answered section
   and on the free-text blob. An LLM cannot suppress, downgrade or override them: EMERGENCY/URGENT
   escalation and `RedFlagAlert` rows are created in the same request as the answer, before/independent
   of any AI call (verified by tests that mock a dismissive/failed LLM).
2. **AI output is quarantined.** LLM summaries/follow-ups pass validation blocklists
   (no dosages, no diagnoses, no reassuring statements). If the LLM is unavailable, follow-ups
   fall back to reviewed ontology questions — the clinical pathway never depends on generated text.
3. **Provenance separation is structural, not cosmetic.** In the doctor dossier,
   verbatim patient statements (`HistoryResponse`), the AI draft (`ClinicalSummary`), OCR-extracted
   entities (`ExtractedEntity`) and red-flag alerts are distinct tables/blocks. Patient answers are
   never mutated by AI or doctor edits.
4. **OCR entities require physician verification.** Every extracted entity starts
   `doctor_verified=False`; only `POST /api/doctor/verify-entity/{id}` (DOCTOR token) flips it,
   with an audit row. Unverified OCR text is labelled as such in the dossier and FHIR bundle.
5. **Signed summaries are immutable to AI.** After sign-off (`confirm=true` → `is_confirmed_by_doctor`,
   encounter `FINALIZED`), regeneration endpoints return **409**, and re-signing a finalized
   encounter returns **409** (double-click/replay safe). Doctor edits are revision-counted and the
   previous state is preserved in the audit log.
6. **OCR is honest about failure.** Empty/failed extraction records `NO_TEXT`/`FAILED` states;
   the pipeline never invents clinical entities for a blank or unreadable scan.
7. **Speech is honest about availability.** `/api/speech/status` reports real per-language
   provider readiness; unavailable providers return 503 and the kiosk falls back to typed input —
   no synthetic "transcripts" are ever fabricated.

## 6. Interoperability Claims — What Is Real

- **FHIR R4 bundle** (`GET /api/fhir/encounter/{id}`) is **locally generated only**. It has not
  been validated against an external FHIR conformance suite and is **not** ABDM-certified.
  Document references use opaque local URLs (`api/documents/file/{id}`).
- **ABDM push** (`POST /api/fhir/abdm/push/{id}`) is a **simulation**: it writes an
  `IntegrationEvent` and returns `SIMULATED_NOT_TRANSMITTED`. No data leaves the machine,
  regardless of `ABDM_*` environment values.

## 7. Data Protection Posture & Remaining Risks

| Area | Status |
|---|---|
| Transport | HTTP on localhost only (dev/proxy setup). No TLS termination in this repo — a real deployment must add it. |
| Data at rest | PostgreSQL (or SQLite fallback) plain tables; uploads in `backend/uploads/` (gitignored). No field-level encryption. TDE/encryption at rest is a deployment responsibility. |
| Secrets | `.env` is gitignored and only `.env.example` is committed; health/diagnostics endpoints print masked previews, never full values. **The handover folder's live `.env` contains a real local PostgreSQL password and a non-default JWT secret — remove or rotate before sharing the project.** |
| Logs | Startup error banners show the DB connection error text (useful for the operator); no request bodies (i.e. no PHI) are written to console logs. |
| Audit | All consent decisions, intake lifecycle, OCR outcomes, verifications, sign-offs, PHI downloads and hash upgrades land in `AuditLog` (append-only writes; no delete endpoint exists). |

### Outstanding risks (honest list)
- No rate limiting, no token revocation, no per-patient doctor assignment (§1).
- Anonymous kiosk writes rely on UUID unguessability (§3).
- Legacy SHA-256 hashes persist until a user logs in once.
- All clinical content must be understood as **synthetic/demo data** — see the demo guide; no real
  patient data has been used in development or testing.
- No pen-testing, no security audit beyond the code-level guards above.

## 8. Regulatory Positioning (must be stated in any showcase)

Academic prototype for classroom/demonstration use. Not for clinical decisions, not a
medical device (CDSCO), not an ABDM Health Account, and not compliant with any production
health-data regulation. FHIR/ABDM pieces exist to demonstrate architecture, clearly labelled
as local/simulated.
