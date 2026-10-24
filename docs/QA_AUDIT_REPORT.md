# MediKiosk — Complete Website Quality Assurance Audit Report

- **Audit date:** 2026-10-23
- **Audit type:** Evidence-based, audit-and-report ONLY. No source code, configuration, dependency, database-schema, or service changes were made. All test artifacts were confined to `scratch/` (git-ignored) and synthetic "QA Probe" records.
- **Auditor scope:** Frontend/UI, patient intake workflow, consent & privacy, OCR & documents, speech & AI, doctor dashboard & clinical workflow, backend APIs & database, security & reliability.

---

## 1. Executive Summary

MediKiosk's **backend is in strong shape**: the fresh pytest suite passed 209/209 (1 skipped), and 43 of 45 live API security/consent/workflow probes passed, confirming correct authentication, role-based authorization, server-enforced consent, deterministic red-flag detection, OCR review-and-verify persistence, sign-off immutability, idempotency, and FHIR generation with honest consent/provenance states. **One deterministic backend bug was found** (on-demand summary regeneration crashes with HTTP 500 before sign-off — BUG-001).

The **frontend is where the meaningful problems live**: the kiosk consent screen ships with all three consent checkboxes pre-checked and offers no decline path (BUG-002, the most serious finding of this audit), the doctor/admin pages have no client-side route guard and silently swallow 401/403 errors (BUG-003/005), in-progress intake answers are lost on Back navigation (BUG-004), and there is no logout UI anywhere (BUG-011). A misleading "NVIDIA Nemotron 3 Ultra" label is shown while the system is actually producing a deterministic template reply (BUG-006).

**Release readiness: NOT READY for real patient use** — suitable for demo/controlled evaluation only. The backend safety guarantees hold, but the consent UX defect (BUG-002) directly contradicts the explicit-consent claims in `docs/SECURITY_AND_CLINICAL_SAFETY.md`, and the 500 on summary regeneration is an unguarded crash on a clinical workflow endpoint.

---

## 2. Project and Test Environment

| Component | Observed state at audit time |
|---|---|
| Backend | FastAPI + uvicorn, started from repo root (`backend.app.main:app`) on `127.0.0.1:8000`. Was DOWN at audit start (previous session terminals closed); started fresh — no existing service was stopped or restarted. |
| Database | Live PostgreSQL at `127.0.0.1:5432/medikiosk_db` (per `/health` diagnostics). Not reset, not migrated, not modified beyond synthetic probe rows. |
| Frontend | Next.js 14.2.24 (`next dev -p 3000`). Was DOWN at audit start; crashed once mid-audit from an environment issue (OneDrive `EINVAL` on `.next`, see §12), restarted. |
| Auth | JWT bearer tokens; seeded DOCTOR/ADMIN accounts (credentials per `docs/WINDOWS_SETUP.md` §4 — not reproduced here). |
| Speech | Whisper local model **available** (`/api/speech/status`: `en`, `hi`, `gu` ready; provider `whisper_local_model`). IndicConformer nemo file present at root but was not load-tested in this audit. |
| OCR | PaddleOCR **available** and working (test document extracted with 91% confidence, `ocr_status=COMPLETED`). |
| LLM | OpenRouter key **not set**; local Ollama **not reachable** (port 11434 closed) → deterministic fallback path active (an environment condition, not a defect — the fallback itself works). |
| Test data | Synthetic only: "QA Probe One/Two/Three", "Browser QA Patient". Real seeded demo records were read but not altered. |
| Tools | `pytest` (backend suite), custom PowerShell HTTP probe harness (`scratch/qa_*.ps1`), `curl.exe` for multipart uploads, browser automation for E2E, `npx tsc --noEmit`, `npm run build`. |
| Platform | Windows, PowerShell 5.1. Workspace under OneDrive (caused documented environment issues, see §12). |

---

## 3. Features Audited

| # | Feature area | Audited how |
|---|---|---|
| A | Frontend/UI: homepage, nav, feature cards, login, intake screens, doctor dashboard, chat, invalid routes, console errors, responsive | Browser E2E + hard reloads + DOM/console inspection |
| B | Patient intake workflow: init, answer, sections, complete, duplicate submit, Back navigation | API probes + browser wizard walk-through |
| C | Consent & privacy: pending/accepted/declined states, bypass prevention, persistence, exposure | API probes (4 states) + consent UI browser inspection + log grep |
| D | OCR & documents: valid/invalid/empty/oversized uploads, extraction quality, review/correct, access control | 12 probe cases (E-series) + real OCR upload + entity verify through the UI's data path |
| E | Speech & AI: transcription, fallbacks, LLM behavior, missing services, output distinguishability | 8 probe cases (F/S-series) + status endpoints + chat UI observation |
| F | Doctor dashboard & clinical workflow: login, queue, records, verification, sign-off, red flags, role access | API probes (C/G-series) + browser workstation inspection |
| G | Backend APIs & DB: status codes, validation, persistence, idempotency, malformed payloads, FHIR | 45-probe HTTP matrix + P0–P-series payload validation + full-cycle probes |
| H | Security & reliability: auth/RBAC, unauthorized access, secrets exposure, error disclosure, repeated requests | L/R-series probes + secret-leak scanner + `.gitignore`/logging review |

---

## 4. Overall QA Results

**Counts below are calculated from tests actually executed in this audit.** Test counts and feature counts are listed separately and must not be conflated.

### Test-execution counts

| Test set | Run | Passed | Failed | Blocked | Not tested |
|---|---|---|---|---|---|
| Backend pytest suite (fresh) | 210 | **209** | 0 | 0 | 1 skipped (by design — optional dependency marker) |
| Live API probe matrix (`qa_api_probes.ps1`) | 45 | **43** | 2 nominal | 0 | 0 |
| ├ both nominal "failures" investigated | | | → **0 confirmed defects** (E1: expected 400, got 415 — a valid rejection; E7: probe-script cast bug, endpoint returned 200 and was re-verified) | | |
| Follow-up probes (full cycle ×2, entity verification ×2, 500-repro) | ~25 assertions | 24 | **1 confirmed defect** (G1: generate-llm-summary → 500, BUG-001) | 0 | 0 |
| Browser E2E steps | 21 | 14 | 5 | 2 (see below) | 0 |
| `npx tsc --noEmit` | 1 | 1 | 0 | 0 | 0 |
| `npm run build` (production) | 1 | 1 | 0 | 0 | 0 |
| Repo-hygiene checks (git tracking, log/PHI grep, secret-leak scan) | 4 | 3 | 0 | 0 | 1 (git checks BLOCKED — no repository exists, see §12) |

### Confirmed bugs by severity

| Severity | Count | IDs |
|---|---|---|
| P0 — Critical | **0** | — |
| P1 — High | **2** | BUG-002, BUG-003 |
| P2 — Medium | **3** | BUG-001, BUG-004, BUG-005 |
| P3 — Low | **5** | BUG-006 – BUG-011 (excl. above) |

### Feature-level outcome (not test counts)

| Status | Features |
|---|---|
| **Working (13)** | Auth+RBAC API, consent enforcement API, red-flag detection, intake session lifecycle+idempotency, OCR upload→extract→review→verify, document download access control, speech transcription+validation+fallbacks, FHIR export w/ consent+provenance, ABDM (honestly simulated), doctor queue+sign-off+immutability, server input validation, login page+workstation rendering, pytest/tsc/build |
| **Partially working (4)** | AI chat UI (works, but misleading model label), kiosk in-page intake wizard (works, but no draft persistence + URL not synced), route hygiene (pages exist, but unstyled 404), responsive layout (passes at emulated 390 px; real-device resize unverified) |
| **Broken (3)** | Consent capture UI (pre-checked, no decline), summary regeneration before sign-off (HTTP 500), client-side session handling (no route guard, no logout, silent auth errors) |

---

## 5. Working Features — With Evidence

Every item below was executed and observed during this audit.

| Feature | Evidence |
|---|---|
| **Auth & RBAC (backend)** | DOCTOR token: queue 200, verify-entity 200, sign-off 200. ADMIN token: verify-entity **403**, sign-off **403** (R-series probes). No/invalid token: queue, audit-logs, documents download, FHIR all **401**. Login without/wrong password or wrong role → **401**; seeded logins → 200 with `access_token`. |
| **Consent enforcement (API)** | `intake/init` → consent `PENDING`. Id mismatch → **400**; unknown encounter → **404**; explicit `granted=true` → 200 and persisted; `granted=false` recorded as DECLINED state machine. FHIR export refuses before consent grant. |
| **Red-flag detection (deterministic)** | SITE "central crushing pain" alone → no flag. Adding RADIATION "spreads to left arm" → `EMERGENCY` flag raised deterministically (rule confirmed at `backend/app/clinical/red_flags.py` L155-172); queue row shows `priority=EMERGENCY` + `red_flag_alerts`. Flag survives session completion. |
| **Intake session lifecycle** | Full cycle: init → consent → 3 answers → upload → complete → 200; repeated complete → 200 with `already_completed=true` (idempotent, no duplicate records). Unknown session → 404; malformed JSON → **422**. |
| **OCR & document pipeline** | Real PNG upload → `ocr_status=COMPLETED`, `overall_confidence≈0.91`, 3 extracted entities with `source_snippet`. `.txt` upload → **415** (valid rejection); empty file → **400**; unknown encounter → **404**; 16 MB file → **413**. |
| **Entity review & verification** | `POST /api/doctor/verify-entity/{id}` → 200 `{"status":"VERIFIED"}`; flag flipped `doctor_verified False→True` **persisted across refetches** (qa_flag_check2.ps1 before/after output). ADMIN attempt → 403. |
| **Sign-off & immutability** | Sign-off → 200; second sign-off → **409**; AI summary regeneration after sign → **409** ("signed record cannot be overwritten"); verified entities not altered by AI path. |
| **Speech transcription** | `/api/speech/status` → whisper ready for en/hi/gu. Valid 16 KB WAV → 200 with transcript (tone file returned EMPTY transcript + confidence 0.0 — honest, no fabricated text). 16 MB → **413**; unsupported language → **400**. |
| **FHIR export** | After consent+sign: 200 with **8 entries** — Patient, Encounter, Consent (`status=active`), Observation, MedicationRequest ×2, DocumentReference, Composition (`status=final`). Before consent grant → refused. |
| **ABDM integration honesty** | Push returns `SIMULATED_NOT_TRANSMITTED` / `SANDBOX_SIMULATION` — the system does not claim a real integration it does not have. |
| **No secrets/PHI in responses or logs** | Probe harness compared `.env` values against `/health` and `/api/health/diagnostics` bodies — no secrets found (boolean check only; values never printed). Grep across `backend/app`: no logging of patient names, answers, or credentials; module-status logs only. |
| **Doctor workstation UI** | Login → `/doctor` queue renders 8–9 rows with token numbers, red-flag badges; opening "Ramesh Kumar" shows records with EMERGENCY flag; OCR entity verified-state renders in UI. |
| **Homepage feature cards** | All 4 cards navigate to `/patient/intake`, `?step=docs`, `?step=review`, `/doctor` and pages render (verified in browser, including hard-reload deep links). Console clean except one expected 401 on unauthenticated `/doctor` queue fetch. |
| **Chat API transport** | `POST /api/chat/message` → 200 structured reply; `/api/chat/prompts` → 200. (UI-level concern noted separately as BUG-006.) |
| **Code-level checks** | `npx tsc --noEmit` exit 0. `npm run build` exit 0 — "✓ Compiled successfully", 9/9 static pages, 7 routes. |

---

## 6. Partially Working Features — With Limitations

| Feature | What works | Limitation (evidence) |
|---|---|---|
| **AI chat UI** (`/chat`) | Page loads, message POST succeeds, structured templated medical responses render. | With no OpenRouter key and no local LLM, replies come from the deterministic fallback, yet the UI displays "NVIDIA Nemotron 3 Ultra formulating medical response…". The label is not tied to actual engine state → misleading (BUG-006). Also `/api/chat/prompts` is fetched twice per page load (BUG-009). |
| **Kiosk in-page intake wizard** (root `/`) | Walks through all steps; `intake/init` succeeds on completion; final records reach the doctor queue (browser test: "Browser QA Patient" appeared in queue with token OPD-188). | Answers are **not persisted between steps** — navigating Back loses the previous answer, which must be re-entered (BUG-004). Only `/api/intake/init` is called during the whole in-page wizard; the rest is a local `clinicalStore` simulation, so in-page answers do not produce server-side Answer records (by design, but not stated in the UI). In-page view switches do not update the URL (BUG-008). |
| **Route hygiene** | `/login`, `/doctor`, `/admin`, `/chat`, `/patient/intake` all render; deep links with `?step=` work after hard reload. | Invalid routes show the **builtin unstyled Next.js 404** (browser default styling, no MediKiosk chrome, no path back) (BUG-007). |
| **Responsive layout** | At emulated 390 px width (same-origin iframe): `scrollWidth (384) = clientWidth`, zero overflowing elements — no horizontal overflow. | Real physical resize could not be performed (automation viewport fixed at 660×372; scripted resize is a no-op). Tablet/desktop breakpoints and native mobile behavior are **NOT TESTED** (§12). |
| **Registration form** (`/login` → register tabs) | Both register tabs submit; success path produces a login that works. | Gender and Department selects are `required=false` — no client-side validation; "First-time" tab relies solely on native HTML5 validation (no styled/custom messaging) (BUG-010). |
---

## 7. Failed Features and Confirmed Bugs

| Feature | Failure | Bug ID |
|---|---|---|
| **Consent capture UI** (kiosk Step3Consent) | ALL THREE consent items render **pre-checked**; "Agree & Continue" advances without any user interaction; **no decline control exists** on the screen. Consent cannot be refused, and agreement cannot be attributed to an explicit user act. | BUG-002 (P1) |
| **On-demand summary regeneration** | `POST /api/doctor/encounter/{id}/generate-llm-summary` returns **HTTP 500** (deterministic) whenever the encounter is still unsigned. Crashes on a nonexistent SQLAlchemy relationship. | BUG-001 (P2) |
| **Client-side route protection** (`/doctor`, `/admin`) | Visiting these pages **without a token renders the full workstation shell** with empty/zeroed data. The 401s are silently swallowed — no redirect to `/login`, no error message, no login prompt. The user sees a "fake-empty" clinical screen. | BUG-003 (P1) |
| **Session termination** | **No logout control exists anywhere** in the UI (kiosk, doctor, admin, chat). The JWT persists in `localStorage` with no way to clear it from the app. | BUG-011 (P3, elevated by finding) |
| **Admin panel error surfacing** | Opening the in-page admin panel with a DOCTOR token fires 4 × `/api/admin/audit-logs` → **403**, all silently ignored; panel shows empty state with no explanation. | BUG-005 (P2) |
| **Intake draft preservation** | Answers typed in the wizard are discarded when the user presses Back and must be re-entered. | BUG-004 (P2) |

Note: the backend is NOT at fault for the auth-related rows — the API correctly returned 401/403 in every case. The defects are client-side handling of those correct responses.

---

## 8. Security and Privacy Findings

### Confirmed correct (verified live — these are not bugs)
- **Authentication**: All protected endpoints reject missing/invalid bearer tokens with 401 (queue, dossier, documents, download, audit-logs, FHIR, verify-entity, sign-off).
- **Role-based authorization**: ADMIN is correctly refused on clinical-action endpoints (verify-entity 403, sign-off 403); DOCTOR is correctly refused on `/api/admin/audit-logs` (403). Verified by direct API calls with both token types.
- **Consent enforcement server-side**: FHIR export and records generation are gated on an explicit consent grant; the API cannot be talked into fabricated consent (mismatched ids → 400, unknown encounter → 404).
- **Immutability**: AI cannot overwrite a signed encounter (409) and cannot alter doctor-verified entities; red flags are raised deterministically by rules, not by LLM output, so an AI failure cannot suppress them.
- **No secrets exposure**: `/health` and `/api/health/diagnostics` bodies were diffed against `.env` values programmatically — no key, password, or token appears. Error bodies return structured messages without stack traces or internal paths.
- **No PHI in logs**: Source grep across `backend/app` found logging of module status, file paths, and model outcomes only — no patient names, answers, or credentials.
- **Upload safety**: Size (16 MB → 413), type (`.txt` → 415), and empty-file (400) rejections all work; uploads use server-generated UUID filenames.
- **Document access control**: Direct download of an uploaded file → 401 without token, 200 with a doctor token. Correct.
- **Honest simulation**: ABDM returns `SIMULATED_NOT_TRANSMITTED` rather than pretending to integrate with a national network.

### Findings (defects/risks)
| ID | Finding | Severity |
|---|---|---|
| SEC-1 | Consent UI collects "agreement" with pre-checked boxes, no decline option, no explicit user action — **invalid as informed consent** even though the backend handles consent correctly. Any consent record originating from the kiosk UI is unverifiable as a patient decision. | **P1** (= BUG-002) |
| SEC-2 | JWT stored in `localStorage` with no expiry handling, no refresh, no invalidation path, and no logout UI — a shared kiosk/clinic device leaves the session open indefinitely; XSS or device access yields the token. | P2 (suspected risk; storage location confirmed, attack not demonstrated) |
| SEC-3 | Unauthenticated `/doctor` and `/admin` render the clinical shell instead of gating on auth — authorization is enforced server-side (good) but the UI leaks the application's structure and creates fake-empty clinical views. | P1 (= BUG-003) |
| SEC-4 | Demo quick-fill credentials **visible on the login page** as buttons. Acceptable for a demo, unacceptable for any real deployment. | P3 (intended demo behavior, flagged as a deployment risk) |
| SEC-5 | 401/403 responses are silently discarded client-side, so users (and reviewers) get no signal that access was denied — a legitimate security response becomes invisible, encouraging repeated unauthorized navigation attempts. | P2 (= BUG-005) |
| SEC-6 | AI-generated chat is labelled with a specific commercial model name while actually running a deterministic fallback — misleading provenance for medical content. | P3 (= BUG-006) |

### Not-tested security areas
Rate limiting/brute-force lockout, CSRF (API is bearer-token based, low relevance), token expiry behaviour, password hashing strength beyond schema inspection, SQL injection beyond ORM usage, dependency vulnerability scan (`npm audit`/`pip-audit` not run — would require tool output not requested), TLS/network hardening (local HTTP dev environment), concurrent load.

---

## 9. UI/UX and Accessibility Findings

| ID | Finding | Severity | Evidence |
|---|---|---|---|
| UI-1 | Consent step requires no interaction and offers no refusal path | **P1** | Browser: three checkboxes checked on mount; "Agree & Continue" advances immediately; no decline button in DOM |
| UI-2 | Unauthenticated doctor/admin pages render as functioning (empty) workstations | **P1** | Browser: direct `/doctor` visit with no token → full shell, no login prompt |
| UI-3 | No logout affordance anywhere | P2 | Browser walk of all pages: no session-ending control found |
| UI-4 | Intake answers lost on Back | P2 | Browser: typed answer gone after Back, re-entry required |
| UI-5 | Invalid route → builtin unstyled 404 with no branding or navigation | P3 | Browser: `/#/does-not-exist` path shows default Next.js 404 |
| UI-6 | Kiosk in-page step changes do not update the URL — no bookmarkable/refreshable state on root route | P3 | Browser: view switches with no URL change (deep-link `?step=` only works on `/patient/intake`) |
| UI-7 | Validation messaging relies on native HTML5 + unvalidated selects on registration | P3 | DOM: Gender/Department `required=false` |
| UI-8 | Silent failure states (no loading/error/empty-state messaging for swallowed 401/403) | P2 | Console shows repeated 403s with no UI change |
| A11y | Feature cards were converted to semantic `<Link>` elements with keyboard access in a prior task (verified this audit: focus + Enter navigates). No other accessibility work audited: colour contrast, ARIA on clinical badges, screen-reader labels, focus traps, and language-switch accessibility are **NOT TESTED**. | — | Not evaluated |

---

## 10. Backend, API, and Database Findings

**Overall: healthy.** All findings are enumerated; nothing else deviated from expectation.

| ID | Finding | Severity | Evidence |
|---|---|---|---|
| API-1 | `generate-llm-summary` raises an unhandled exception → HTTP 500 on the unsigned path (see BUG-001) | P2 | Server traceback: `AttributeError: type object 'MedicalDocument' has no attribute 'medications'` at `doctor_router.py:552` |
| API-2 | Test-coverage gap: the above shipped despite 209 passing tests — the unsigned regeneration path is never exercised | P2 (process) | Endpoint absent from all test files; confirmed by grep and by the passing suite |
| API-3 | Endpoint not wired into the frontend (only `verify-entity` is called by the workstation), which limits the user impact of API-1 | Observation | grep of `frontend/src` for `generate-llm-summary` → no matches |
| API-4 | Minor probe-expectation corrections (not defects): `.txt` upload returns 415 not 400 (valid); dossier endpoint returns 200 where an earlier probe line reported failure (script bug) | — | Re-verified in `qa_followup2.ps1` |
| DB-1 | Persistence and consistency confirmed: entities, consent state, red flags, verification flags, sign-off state, and FHIR entries all survive refetches and process restarts during the audit | Pass | before/after probe outputs |
| DB-2 | Idempotency confirmed at the DB level: duplicate `complete` and duplicate sign-off produce no duplicate rows (same ids on refetch) | Pass | probes |
| DB-3 | **Audit leftovers requiring cleanup (not an application defect):** synthetic `QA Probe Patient/Two/Three` (multiple) and `Browser QA Patient` (OPD-188) records, 16 MB `scratch/qa_big.wav`, `.next_stale_qa/` folder, and `scratch/qa_*.ps1|json` artifacts remain from this audit | P3 (hygiene) | Listed in §15 checklist |
| DB-4 | No git repository exists (`git ls-files` → "not a git repository"), so `.env`/DB tracking could not be audited. `.gitignore` correctly excludes `.env`, `*.db`, `backend/uploads/*`, `.next/`, `scratch/` — protection is configured but **unverified against an actual index**. | P2 (suspected risk) | Command output |

**Response-shape reference (used by the probes, for the fix team):**
- Queue item keys: `encounter_id, patient_id, token_number, patient_name, age, gender, mrn, department, status, priority, priority_weight, kiosk_id, created_at, summary_preview, is_confirmed, estimated_intake_minutes, red_flag_alerts`.
- Dossier keys: `patient, encounter, summary, patient_statements, memory_graph, timeline, documents, medications, observations, allergies, surgeries`.
- Upload response keys: `document_id, document_type, ocr_status, overall_confidence, medications_count, observations_count, ocr_engine_available, message, entities` (entity field is `verified`).
- Dossier entity field is `doctor_verified` (with `id, type, name, value, confidence, source_snippet`) under `documents[].extracted_entities`.

---

## 11. Automated Test Results

### Backend pytest (fresh run this audit)
```
209 passed, 1 skipped, 868 warnings in 52.57s
```
Suites run: `test_api_flow`, `test_chat_router`, `test_clinical_ontology`, `test_fhir_serializers`, `test_intake_time_model`, `test_ml_pipeline`, `test_speech_and_ocr`.
- 1 skip: optional-dependency-marked test (environment), not a failure.
- 868 warnings observed (largely library/deprecation noise) — not investigated to defect level; recommended cleanup item.
- **Coverage gap identified**: 209 passing tests still miss the `generate-llm-summary` unsigned path (BUG-001 shipped green).

### Frontend
| Check | Result |
|---|---|
| `npx tsc --noEmit` | **PASS** — exit code 0, no diagnostics |
| `npm run build` | **PASS** — exit 0, "✓ Compiled successfully", "✓ Linting and checking validity of types", 9/9 static pages generated across 7 routes |

Build route map (all prerendered static): `/`, `/_not-found`, `/admin`, `/chat`, `/doctor`, `/login`, `/patient/intake`. Shared first-load JS 87.1 kB; largest page bundle `/` at 5.7 kB (159 kB first load).

> Note for whoever re-runs this: `npm run build` deletes/recreates `.next` and **kills a running `next dev` server** (observed twice). Run builds only when the dev server can be restarted afterwards.

### Custom API probe harness (this audit)
- `scratch/qa_api_probes.ps1` — 45 cases across auth (A), consent (B), RBAC (C/R), payload validation (P), documents/OCR (E), speech (F/S), doctor workflow (G), FHIR/ABDM (H): **43 PASS, 2 nominal FAIL (both resolved as non-defects), 10 INFO**.
- `scratch/qa_followup2.ps1` — single-drain full lifecycle incl. red-flag trigger, OCR, complete, sign-off, 409 immutability, FHIR (8 entries) + **BUG-001 reproduction**.
- `scratch/qa_followup3.ps1`, `qa_flag_check.ps1`, `qa_flag_check2.ps1` — entity verification truth-cycles (upload → dossier → verify → persist → ADMIN 403).

---

## 12. Blocked and Untested Areas — With Reasons

| Area | Status | Reason |
|---|---|---|
| Real viewport responsive breakpoints (320/768/1024/1440) | **BLOCKED** | Automation viewport fixed at 660×372; scripted `resizeTo` is a no-op. Partially mitigated by same-origin 390 px iframe measurement (no overflow detected). |
| Screenshot-based visual verification | **BLOCKED** | Browser window minimized during the session — no physical clicks/keys/screenshots. Evidence gathered via DOM inspection, `element.click()`, network logs, and HTTP status instead. |
| IndicConformer 600M speech model actual inference | **NOT TESTED** | Whisper provided the working path for en/hi/gu; the `.nemo` model's runtime was not load-tested (heavy, environment-specific). Recorded as an environment limitation — Whisper fallback works. |
| Live LLM behaviour (OpenRouter / Ollama) | **NOT TESTED (unavailable)** | No OpenRouter key in effect; Ollama not listening on 11434. Deterministic fallback was instead verified to behave safely. |
| Full admin surface (`/admin` CRUD, user management) | **PARTIALLY NOT TESTED** | Admin API probes (403/200 rules) passed; admin UI screens beyond the audit-log panel were not walked. |
| Load / concurrency / stress | **NOT TESTED** | Only sequential repeated requests (idempotency) were run; no concurrency harness. |
| Database reset/migration behaviour | **NOT TESTED (intentionally)** | Brief prohibits DB-destructive operations; live PostgreSQL was used read-mostly with synthetic writes only. |
| Dependency vulnerability scanning (`npm audit`, `pip-audit`) | **NOT TESTED** | Not run — would add tool output outside the requested evidence set; no packages installed. |
| Clean-room install from `README`/`docs/WINDOWS_SETUP.md` | **NOT TESTED** | Existing environment reused; a from-scratch install would have required creating new venvs/node_modules (side effects on the machine). |
| Docker path (`docker-compose.yml`) | **NOT TESTED** | Local processes used; bringing up containers would compete with running services. |
| Multi-language kiosk flows (hi/gu UI) with real speakers | **NOT TESTED** | Language validity and model availability were verified at the API level; no real non-English audio was captured. |
| Accessibility audit (contrast, ARIA, screen reader) | **NOT TESTED** | No a11y tooling in scope; only keyboard activation of the newly linked feature cards was verified. |
| Print/QR/paper slip, kiosk physical hardware integration | **NOT TESTED** | Not implemented in the repository beyond token numbers. |

---

## 13. Detailed Bug Register

### BUG-001 — HTTP 500 on on-demand summary regeneration for unsigned encounters
- **Severity:** P2 — Medium
- **Module:** Backend · Doctor API (`backend/app/api/doctor_router.py`)
- **Reproduction:**
  1. Start the backend and log in as a DOCTOR (`POST /api/auth/login`).
  2. Create an encounter through `POST /api/intake/init` → consent → answers → `POST /api/intake/complete/{session_id}` (do **not** sign off).
  3. `POST /api/doctor/encounter/{encounter_id}/generate-llm-summary` with the doctor bearer token.
- **Expected:** A regenerated summary draft (or a clean 4xx if regeneration is not permitted pre-signature).
- **Actual:** **HTTP 500**, deterministically, on every call. Confirmed twice (`qa_api_probes.ps1` G1 and `qa_followup2.ps1`).
- **Evidence:** Backend traceback: `AttributeError: type object 'MedicalDocument' has no attribute 'medications'` at `doctor_router.py:552` — `selectinload(MedicalDocument.medications), selectinload(MedicalDocument.observations)`. Lines ~560-561 then iterate `d.medications` / `d.observations`. After sign-off the same request returns 409 (the immutability guard fires before the crash), proving the crash is in this code path only.
- **Likely root cause (evidence-backed):** `MedicalDocument` defines only `patient` and `extracted_entities` relationships (verified in `backend/app/models/entities.py`); the loader and loops were written against a different/older document shape.
- **Severity rationale:** Deterministic unhandled crash on a clinical endpoint (worse than P3), but the endpoint is **not called by any frontend page** (grep confirmed), so no user-facing workflow is blocked → P2, not P1.
- **Recommended fix:** Replace the eager loaders and loops with `MedicalDocument.extracted_entities` filtered by `entity_type` (`MEDICATION` / `OBSERVATION`), matching how the dossier endpoint already assembles medications/observations. Add a test that calls this endpoint on an unsigned encounter (the gap that let it ship).

### BUG-002 — Consent screen pre-checks all consent items and provides no decline path
- **Severity:** P1 — High
- **Module:** Frontend · Kiosk intake (Step3Consent, root route)
- **Reproduction:**
  1. Open `http://localhost:3000/`, start the intake wizard, advance to the consent step.
  2. Observe the three consent checkboxes; click "Agree & Continue" without touching any checkbox.
- **Expected:** All consent items unchecked; the continue control disabled until the patient explicitly opts in; an explicit decline path that records a DECLINED state.
- **Actual:** All three boxes are **checked on mount**, "Agree & Continue" advances with **zero user interaction**, and **no decline control exists**.
- **Evidence:** Browser E2E DOM inspection of Step3Consent; screenshots unavailable (minimized window) so DOM state is the evidence. Contrast with the backend, which correctly enforces explicit consent (B-series probes: PENDING → explicit grant → 200; mismatch → 400).
- **Likely root cause (evidence-backed):** UI initialises consent state as `true` and no "Decline" handler is rendered — the component treats consent as a formality rather than a decision.
- **Severity rationale:** This is a privacy/regulatory defect, not cosmetic: it invalidates consent as an explicit patient act and contradicts the documented explicit-consent guarantee. Not P0 because the backend still refuses to export records without an API-level grant, and no data leak or breach was demonstrated.
- **Recommended fix:** Start unchecked; disable the agreement button until all required items are actively checked; add a visible "Decline" control that submits `granted=false` to `POST /api/intake/consent` and ends the session gracefully; record a timestamp + principal for the decision; ensure the wizard actually calls the consent endpoint rather than only storing state locally.

### BUG-003 — No client-side route guard on `/doctor` and `/admin`; auth errors silently swallowed
- **Severity:** P1 — High
- **Module:** Frontend · routing/session (`frontend/src/app/doctor`, `/admin`, `frontend/src/lib/auth.ts`)
- **Reproduction:**
  1. Clear site data / open a fresh context. Navigate directly to `http://localhost:3000/doctor` (or `/admin`).
  2. Observe: the workstation shell renders with empty lists and no prompt.
- **Expected:** Redirect to `/login` (or render an explicit "sign in required" state) when no valid token exists.
- **Actual:** Full clinical UI renders; the queue request 401s and the failure is discarded. Same for `/admin`.
- **Evidence:** Browser E2E (unauthenticated visits) + console showing 401 on `/api/doctor/queue`; earlier feature-card test produced the same observation. Server behaviour is correct (401 confirmed by probes) — the defect is the client.
- **Likely root cause (evidence-backed):** No route-level guard/middleware and no shared fetch wrapper that handles 401 by redirecting; component-level `catch` paths leave empty state.
- **Severity rationale:** Not a data breach (the API refuses), but it presents a convincing fake clinical interface to unauthorized visitors and gives no security feedback — a significant authorization/UX failure in a medical app.
- **Recommended fix:** Add an auth guard (Next.js middleware for cookie-based auth, or a shared client-side layout guard reading `localStorage` token) redirecting to `/login?next=…`; centralise API calls in a wrapper that on 401 clears the token and redirects, and on 403 renders a distinct "insufficient role" message.

### BUG-004 — Intake wizard loses entered answers on Back navigation
- **Severity:** P2 — Medium
- **Module:** Frontend · kiosk intake wizard
- **Reproduction:** Start the wizard → type an answer in step N → press Next → press Back → the field is empty; the answer must be retyped.
- **Expected:** Entered responses are preserved when navigating back (and ideally recoverable after an accidental refresh).
- **Actual:** No draft persistence — answers are discarded on Back.
- **Evidence:** Browser E2E repeated-navigation test; `localStorage` holds only the `medikiosk_state_v3` store, not in-progress answers.
- **Likely root cause (evidence-backed):** Step components hold local state that is unmounted on navigation; the store is not updated per answer.
- **Recommended fix:** Lift per-answer state into the store (or `sessionStorage`) keyed by section/question id and rehydrate on mount; keep completed-step values visible when revisiting.

### BUG-005 — Admin panel 403 failures are silent (no message, no state change)
- **Severity:** P2 — Medium
- **Module:** Frontend · in-page admin panel
- **Reproduction:** Log in as a DOCTOR, open the admin panel → 4 × `GET /api/admin/audit-logs` return 403; the panel renders as empty with no explanation, and the requests repeat.
- **Expected:** A single clear "you do not have permission to view audit logs (requires ADMIN)" message, with no retry loop.
- **Actual:** Four ignored 403s, empty panel, repeated fetches.
- **Evidence:** Browser console/network log during the E2E admin-panel step.
- **Likely root cause (evidence-backed):** Fetch calls without status handling, re-invoked per render cycle.
- **Recommended fix:** Handle 403 explicitly with a message; hide the panel for non-ADMIN roles; fix the double/repeat-fetch (dependency array or request de-duplication).

### BUG-006 — Chat UI credits a commercial LLM while returning deterministic fallback text
- **Severity:** P3 — Low (cosmetic/messaging, but with trust implications — see SEC-6)
- **Module:** Frontend · `/chat`; backend `llm_service` status not surfaced
- **Reproduction:** With no OpenRouter key configured, open `/chat`, send a message → the interface displays "NVIDIA Nemotron 3 Ultra formulating medical response…" while the reply is the deterministic template.
- **Expected:** The label reflects the actual engine, e.g. "Deterministic clinical fallback (no LLM configured)".
- **Actual:** Fixed model name displayed regardless of engine state.
- **Evidence:** Browser observation of the loading label; `/api/health/diagnostics` + backend logs show `OPENROUTER_API_KEY is not set … Engaging clinical deterministic fallback`; replies are structurally identical templates.
- **Likely root cause (evidence-backed):** Hard-coded frontend string; no engine-state field consumed from the API (a status endpoint exists but is not used for this label).
- **Recommended fix:** Expose the active engine in the chat response/status payload and render it; never name a model that is not producing the output.

### BUG-007 — Unstyled builtin 404 on invalid routes
- **Severity:** P3 — Low | **Module:** Frontend routing
- **Reproduction:** Visit any undefined path (e.g. `/does-not-exist`) → default Next.js 404 page (no MediKiosk header/footer/branding, no navigation).
- **Expected:** Branded "Page not found" with a link home (and role-appropriate suggestions).
- **Evidence:** Browser DOM inspection. **Fix:** add `frontend/src/app/not-found.tsx`.

### BUG-008 — Kiosk in-page step navigation does not update the URL
- **Severity:** P3 — Low | **Module:** root-route state machine
- **Reproduction:** On `/`, switch between kiosk views → URL stays `/`; views are unbookmarkable and unavailable to Back/refresh (the standalone `/patient/intake` route does support `?step=` deep links).
- **Evidence:** Browser URL check during view switches. **Fix:** `router.replace` (or query param) on step change, mirroring the intake page's effect.

### BUG-009 — `/api/chat/prompts` fetched twice per page load
- **Severity:** P3 — Low | **Module:** `/chat` data fetching
- **Evidence:** Network log shows two identical requests on a single mount (React double-effect / missing de-duplication). **Fix:** guard the effect or use a shared client-side cache.

### BUG-010 — Registration form selects unvalidated; validation relies on native HTML5
- **Severity:** P3 — Low | **Module:** `/login` register tabs
- **Reproduction:** Open the register form → Gender and Department `<select>`s are `required=false` → submit with defaults; the "First-time" tab has only browser-native messages, which fail on some kiosk browsers/assistive tech.
- **Expected:** Required selection validated with styled feedback consistent with other fields; server-side validation confirmed as the backstop.
- **Evidence:** DOM attribute inspection. **Fix:** mark required + add explicit messaging.

### BUG-011 — No logout control anywhere in the application
- **Severity:** P3 — Low by classification, P2-equivalent on shared devices (flagged for prioritisation in §14)
- **Module:** Frontend · session management
- **Reproduction:** Log in as doctor/admin → search every page for a sign-out control → none exists. The JWT remains in `localStorage` until manually cleared.
- **Expected:** Persistent session-ending control that clears the token and redirects to `/login`.
- **Evidence:** Full browser walk of `/`, `/chat`, `/doctor`, `/admin`, `/login`, `/patient/intake`.
- **Fix:** Add a header sign-out action calling `localStorage.removeItem('medikiosk_token')` and redirecting; if the backend adds a revocation/list endpoint, call it first.

---

## 14. Prioritised Fix Recommendations

Fix order below is by severity × clinical risk. **No code was changed by this audit.**

| Priority | Action | Target |
|---|---|---|
| **1 (P1)** | Fix consent UI: start unchecked, gate the button on explicit opt-in, add a real Decline path that POSTs `granted=false`, stamp the decision, and actually call the consent API from the wizard (BUG-002 / SEC-1) | kiosk Step3Consent |
| **2 (P1)** | Add route guards for `/doctor` and `/admin` + central 401→login / 403→message handling (BUG-003, BUG-005 / SEC-3, SEC-5) | Next.js middleware or shared client guard + API wrapper in `src/lib` |
| **3 (P2)** | Fix `generate-llm-summary` crash using `extracted_entities` filtered by entity type; add a regression test for the **unsigned** path (BUG-001, API-2) | `backend/app/api/doctor_router.py` L549-562 |
| **4 (P2)** | Persist in-progress intake answers across Back/refresh (BUG-004) | kiosk wizard + store/sessionStorage |
| **5 (P2)** | Add logout: clear token, redirect; consider short token expiry + refresh (BUG-011, SEC-2) | Frontend header + auth module |
| **6 (P2)** | Initialise git and verify `.env`, `*.db`, `backend/uploads/*` are truly untracked; add a pre-commit secret scan (DB-4) | repo root |
| **7 (P3)** | Make the chat engine label reflect the real active engine (BUG-006 / SEC-6) | chat UI + response/status payload |
| **8 (P3)** | Branded `not-found.tsx`; URL-sync kiosk steps; de-duplicate chat prompt fetch; validate register selects | frontend |
| **9 (P3)** | Move demo quick-fill credentials behind an explicit "demo mode" flag and remove them from any public/staging build (SEC-4) | login page |
| **10** | Address the 868 pytest warnings and doc/README claims audit (keep "simulated"/"sandbox" language everywhere) | tests + docs |
| **11** | Clean audit leftovers before hand-off (see §15, last block) | environment |

---

## 15. Manual Testing Checklist

Re-runnable checklist for the next tester. Steps assume backend on `:8000`, frontend on `:3000`, seeded DOCTOR/ADMIN accounts (see `docs/WINDOWS_SETUP.md` §4 — do not hard-code them).

**Environment / startup**
- [ ] `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` from the **repo root** (running from `backend/` fails with `ModuleNotFoundError: No module named 'backend'`)
- [ ] `GET /health` → 200; check `database` connector and `module_status` (speech, ocr, llm)
- [ ] `GET /api/speech/status` → languages ready; `GET /api/health/diagnostics` → no secrets in body

**Backend suites**
- [ ] `pytest` → expect 209 passed / 1 skipped
- [ ] `cd frontend; npx tsc --noEmit` → exit 0
- [ ] `npm run build` → exit 0 (**stop `next dev` first — the build wipes `.next` and kills the dev server**)

**Auth & RBAC (API)**
- [ ] Login DOCTOR/ADMIN → 200 + `access_token`
- [ ] Login with wrong/absent password or mismatched role → 401
- [ ] No token → 401 on `/api/doctor/queue`, `/api/doctor/patient/{id}`, `/api/admin/audit-logs`, `/api/fhir/...`, document download
- [ ] ADMIN token → 403 on `/api/doctor/verify-entity/{id}` and sign-off
- [ ] DOCTOR token → 403 on `/api/admin/audit-logs`

**Consent**
- [ ] `POST /api/intake/init` → `consent_status=PENDING`
- [ ] Consent with mismatched patient/encounter ids → 400; unknown encounter → 404
- [ ] `granted=true` → 200 and reflected in records/FHIR (`Consent.status=active`); `granted=false` → DECLINED
- [ ] FHIR export before grant → refused
- [ ] **UI:** consent step shows unchecked boxes, requires explicit action, and offers a decline path → **currently FAILS (BUG-002)**

**Intake workflow**
- [ ] init → answers → complete → 200; repeat complete → `already_completed=true` and no duplicate rows
- [ ] Unknown session → 404; malformed JSON → 422; missing required fields → 422
- [ ] Red flag: central/crushing pain + radiation to left arm → `EMERGENCY` in `/api/doctor/queue` (`red_flag_alerts` non-empty); site-only case → no flag
- [ ] **UI:** Back navigation preserves answers → **currently FAILS (BUG-004)**

**Documents / OCR**
- [ ] Upload a synthetic prescription image → `ocr_status=COMPLETED`, entities with `source_snippet`, confidence reported
- [ ] `.txt` → 415; empty file → 400; unknown encounter → 404; ~16 MB → 413
- [ ] `verify-entity/{id}` → 200 `{"status":"VERIFIED"}`; re-fetch dossier → `documents[].extracted_entities[].doctor_verified=true` (persisted)
- [ ] Download file without token → 401; with doctor token → 200
- [ ] Missing required data is reported as missing, never invented — confirm extracted entities map to real OCR text

**Speech**
- [ ] Valid WAV (tone/speech) → 200; a tone file yields empty transcript with confidence 0.0 (honest, no fabricated text)
- [ ] Oversized → 413; unsupported language → 400
- [ ] Model unavailable → graceful status/fallback rather than a 500

**Doctor dashboard**
- [ ] Queue loads with token numbers, department, priority, `estimated_intake_minutes`
- [ ] Open patient → statements verbatim, summary with `revision_count`/`is_confirmed`, documents, meds/observations/allergies
- [ ] Sign-off → 200; second sign-off → 409; `generate-llm-summary` after sign → 409; **before sign → currently 500 (BUG-001)**
- [ ] Verified entities survive AI regeneration
- [ ] Unauthenticated direct visit to `/doctor` → **should redirect to login; currently renders empty shell (BUG-003)**

**FHIR / ABDM**
- [ ] Export after consent+sign → 200, 8 entries incl. Consent `active` and Composition `final`
- [ ] ABDM push → `SIMULATED_NOT_TRANSMITTED` (must never claim real transmission)

**Frontend browser pass**
- [ ] All 4 homepage cards navigate to correct routes (incl. hard-reload deep links)
- [ ] Login → doctor queue; records + red-flag badge render; OCR verified-state renders
- [ ] `/chat` sends and receives; engine label matches configuration state (currently FAILS, BUG-006)
- [ ] Invalid route → branded 404 (currently FAILS, BUG-007)
- [ ] Console: no unexpected errors beyond legitimate 401 on unauthenticated queue
- [ ] Logout control exists (currently FAILS, BUG-011)
- [ ] 320/768/1024/1440 px visual check on a real device (could not be done in this audit)

**Audit cleanup (perform before hand-off — these were created by this audit)**
- [ ] Remove synthetic `QA Probe One/Two/Three` and `Browser QA Patient` (OPD-188) rows from the application database (application-level delete only; do not drop/migrate the database)
- [ ] Delete `scratch/qa_*.ps1`, `scratch/qa_*.json`, `scratch/qa_big.wav`, and `frontend/.next_stale_qa/`

---

## 16. Overall Release Readiness Assessment

**Verdict: NOT READY for production or real patient use. READY for controlled internal demo only.**

**Ready (evidence-backed):** The clinical safety core is real and works under test — deterministic red flags that AI cannot suppress, server-enforced consent gating on exports, sign-off immutability with 409 protection against AI/revision overwrite, OCR review-and-verify with persisted provenance, correct auth/RBAC on every probed endpoint, idempotent writes, robust input/size/type validation, honest simulation of ABDM, and no secrets or PHI leakage in responses or logs. 209/209 backend tests pass with zero type errors and a clean production build.

**Not ready:**
1. **Consent capture is not valid consent** (BUG-002). Pre-checked boxes with no decline option means any patient-facing deployment would be making a privacy claim the UI cannot support. This is the single blocking issue.
2. **Clinical screens are reachable without authentication** (BUG-003). Authorization holds server-side, but an unauthorized visitor sees a convincing workstation — unacceptable in a clinical tool.
3. **An unhandled 500 exists on a doctor workflow endpoint** (BUG-001), and 209 green tests did not catch it — the test suite needs a regression test on the unsigned regeneration path before release.
4. **Session management is incomplete** — no logout, no client-side token expiry handling (BUG-011/SEC-2), which is unsafe on shared kiosk/clinic devices.
5. **AI-output provenance is misleading** (BUG-006) and **unverified areas remain**: real multi-breakpoint responsive behaviour, IndicConformer inference, live-LLM behaviour, load/concurrency, dependency vulnerability scanning, clean-room install, Docker path, and accessibility (contrast/ARIA/screen readers).
6. **No version control in the audited tree** (DB-4) — protections exist in `.gitignore` but there is no repository to prove secrets and patient uploads stay out of history.

**Minimum gate to call this demo-safe:** fix BUG-002, BUG-003, BUG-001; add the missing regression test; then re-run §15 end to end. **Minimum gate for real patient use:** all of the above plus logout/token expiry, truthful AI labelling, accessibility and responsive verification, dependency scan, clean-room install verification, git init with secret scanning, and removal of demo credentials.

---

### Evidence index (all under `scratch/`, git-ignored; created for this audit only)

| Artifact | Purpose |
|---|---|
| `qa_api_probes.ps1` | 45-case HTTP matrix (auth, consent, RBAC, validation, documents, speech, doctor workflow, FHIR/ABDM, secret-leak scan) |
| `qa_followup2.ps1` | Full lifecycle single-drain cycle + BUG-001 reproduction |
| `qa_followup3.ps1`, `qa_flag_check.ps1`, `qa_flag_check2.ps1` | Entity verification truth-cycles and ADMIN 403 |
| `p7_ocr_smoke.png` | Synthetic prescription image used as OCR input (pre-existing fixture, reused) |
| `test_audio/test_tone_16k.wav`, `test_tone_short.wav` | Speech probe inputs (pre-existing fixtures, reused) |

*No application source, configuration, dependency manifest, database schema, or existing service was modified during this audit.*