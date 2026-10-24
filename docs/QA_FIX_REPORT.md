# MediKiosk — Phase 9 QA Fix Report (Autonomous Bug Fixing + Live Browser QA)

Scope: Fix the confirmed defects in [`docs/QA_AUDIT_REPORT.md`](./QA_AUDIT_REPORT.md), run the
application, and verify each fix through automated tests **and** real browser interactions.

Environment used for verification (unchanged by this work):
- Backend: FastAPI + uvicorn, `127.0.0.1:8000`, started from repo root with the **global** Python
  (`.../Python312/python.exe`) — no `--reload`, so the process was restarted after each backend edit.
- Frontend: Next.js 14.2.24 dev server on `127.0.0.1:3000`.
- Database: live PostgreSQL `medikiosk_db`. **Not reset, not migrated, not deleted.** Only synthetic
  QA rows created during testing; no real/seeded clinical record was overwritten. No signed encounter
  was modified. No red-flag rule was changed.
- LLM: no OpenRouter key, no reachable local Ollama → the deterministic clinical fallback path is active
  (an environment condition, not a defect).
- Browser automation: `browser-use` MCP (navigate / snapshot / click / fill / evaluate_script /
  network & console listing / screenshot). `take_screenshot` succeeded for the Group 1/2 checks; during
  Group 3 the native browser viewport reported `visible=false` (`NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`),
  so Group 3 evidence is DOM/a11y-snapshot + network + console based, which is recorded honestly below.

---

## 1. Priority bugs (§2 order)

### BUG-002 — Consent capture (P1) — FIXED & VERIFIED
- **Root cause:** `Step3Consent` rendered all three consent items pre-checked and exposed no decline
  control, so "Agree & Continue" advanced with zero user action; consent could not be attributed to an
  explicit act nor refused.
- **Fix:** every checkbox starts unchecked; the primary action is disabled until the required consent
  items are explicitly accepted; a functional decline path is added; the existing backend consent API is
  called with the correct decision; API failures surface an error state and never masquerade as success.
- **Files changed:** `frontend/src/components/kiosk/Step3Consent.tsx` (state/labels/handlers + error UI),
  wiring through `frontend/src/app/page.tsx` and `frontend/src/app/patient/intake/page.tsx`.
- **Browser steps:** open kiosk → consent step shows 3 unchecked boxes, primary CTA disabled; tick
  required items → CTA enables → Accept → advances and persists; reload mid-step → boxes return to
  unchecked (no stale acceptance); Decline → refusal captured/redirect; forced API failure → visible
  error, no false success.
- **Evidence:** `scratch/p9_consent_unchecked.png`, `scratch/p9_consent_after_refresh_unchecked.png`,
  `scratch/p9_consent_declined_panel.png`, `scratch/p9_consent_api_failure.png`.
- **Backend verification:** consent state persisted via the existing consent endpoint (checked with safe
  synthetic data only).
- **Result: PASS.**

### BUG-003 — Doctor/Admin route protection (P1) — FIXED & VERIFIED
- **Root cause:** `/doctor` and `/admin` rendered the full workstation shell with no client guard; the
  401/403 responses from the (correct) backend were silently swallowed → a "fake-empty" clinical screen.
- **Fix:** a `RequireAuth` client guard validates the session against `/api/auth/me` (server role, never
  client token claims); unauthenticated users are redirected to `/login?next=<dest>` (same-origin, safe
  target only); 401 clears the session and redirects **without** loops; 403 shows a forbidden panel and
  issues no privileged requests. Server-side auth + RBAC are unchanged. Login/authorization was not
  bypassed or weakened to make any test pass.
- **Files changed:** `frontend/src/lib/auth.ts` (`authFetch`, `clearAuthSession`, `loginUrlFor`,
  `safeNextTarget`), `frontend/src/components/common/RequireAuth.tsx`, `frontend/src/app/doctor/page.tsx`,
  `frontend/src/app/admin/page.tsx`, `frontend/src/app/login/page.tsx` (honors `?next=`).
- **Browser steps (6 cases, all PASS):**
  1. Unauthenticated `/admin` → redirected to `/login?next=%2Fadmin`.
  2. Authorized DOCTOR via the real login form → `/doctor` live queue 200, no error banners.
  3. DOCTOR on `/admin` → forbidden panel, **zero** `/api/admin/*` requests issued.
  4. Invalid token + client-faked ADMIN role → server 401 on `/api/auth/me` cleared session and redirected
     with no loop; the forged client role was **not** trusted.
  5. Refresh on an authorized page → session preserved, data reloads.
  6. Authorized ADMIN on `/admin` → feeds 200, console clean.
- **Evidence:** `scratch/p9_doctor_authorized.png`, `scratch/p9_admin_forbidden_doctor.png`,
  `scratch/p9_invalid_token_redirected_login.png`, `scratch/p9_admin_authorized.png`.
- **Result: PASS.**

### BUG-001 — On-demand LLM summary HTTP 500 (P2) — FIXED & VERIFIED
- **Root cause:** `doctor_router.generate-llm-summary` eagerly loaded `MedicalDocument.medications` /
  `MedicalDocument.observations`, but **those ORM relationships do not exist** on the model — SQLAlchemy
  raised `AttributeError` at query-build time, giving a deterministic 500 for any unsigned encounter
  regardless of documents. The real OCR data lives in `ExtractedEntity` rows keyed by `entity_type`.
- **Fix:** build the LLM context from `selectinload(MedicalDocument.extracted_entities)` and map
  `MEDICATION`→`medications[]`, `LAB_VALUE`→`observations[]` using the existing columns
  (`entity_name`/`entity_value`). The sign-off check (409) still runs **before** any LLM call; the audit
  log (`LLM_SUMMARY_REGENERATED`) is preserved; no signed encounter is overwritten.
- **Files changed:** `backend/app/api/doctor_router.py`; regression tests in
  `backend/tests/test_integration_phase7.py` (`TestLlmSummaryOnDemandFix`).
- **Regression tests added (4, all pass):** unsigned-with-docs→200 SUCCESS (Paracetamol/HbA1c mapped);
  unsigned-without-docs→200; signed encounter→409 with **no** second LLM call; RBAC unchanged
  (no token→401, `NURSE`→403).
- **Live API verification:** restarted backend; authorized DOCTOR probe on synthetic data returned
  **HTTP 200 SUCCESS** using the deterministic fallback (honest — no live LLM), and the summary persisted
  as **UNSIGNED** (probed via `scratch/p9_llm_summary_check.ps1`, `scratch/p9_dossier_check.ps1`).
- **Result: PASS.**

---

## 2. Regression checks after the three priority bugs (§5)

| Check | Command | Result | Exit code |
|---|---|---|---|
| Backend suite (post-priority) | `pytest -q` | 213 passed, 1 skipped | 0 |
| Types | `npx tsc --noEmit` | no type errors | 0 |
| Production build | `next build` (dev stopped first) | ✓ Compiled, 9 routes | 0 |
| Browser recheck | ADMIN `/admin` authorized; roles re-walked | PASS | — |

`.next` build note: the first build attempt failed with `EINVAL readlink` (a OneDrive-materialized
placeholder inside the regenerable `.next` cache). `.next` is gitignored build output — **not** a QA
record, DB, or source — so it was cleared with `Remove-Item -Recurse -Force .next` and the rebuild
succeeded (exit 0). The dev server was then restored.

---

## 3. Group 2 — remaining issues (§6, small group + retest)

### BUG-004 — Intake draft persistence (P2) — FIXED & VERIFIED
- **Root cause:** wizard answers lived only in `SymptomHistoryInterview` local state, lost on Back.
  First attempt (effect-based hydration) **failed under React StrictMode dev double-mount** — the autosave
  effect wrote stale-empty values and clobbered the stored draft before the queued `setState` landed.
- **Fix:** hydrate via lazy `useState(() => ...)` initializers reading `localStorage`
  (`medikiosk_interview_draft_<patientId>`), a single idempotent autosave effect, and `removeItem` on
  completion. Matches the codebase's existing lazy-init pattern (`page.tsx` `useState(() => ...)`).
- **Files changed:** `frontend/src/components/kiosk/SymptomHistoryInterview.tsx`.
- **Browser:** answers persist across Back-navigation **and** refresh; cleared on completion; red-flag
  behavior unchanged; console clean. Evidence: `scratch/p9_bug004_draft_persisted.png`. **PASS.**

### BUG-005 — Admin panel 403 surfacing (P2) — FIXED & VERIFIED
- Handled as part of the BUG-003 guard work: `authFetch` no longer swallows 401/403; a DOCTOR opening the
  admin panel sees an explicit forbidden state and the app issues **no** `/api/admin/*` requests.
  Evidence: `scratch/p9_admin_forbidden_doctor.png`. **PASS.**

### BUG-011 / SEC-2 — Logout control (P3→P2 on shared devices) — FIXED & VERIFIED
- **Fix:** a header Sign-Out action on the staff surfaces clears the session
  (`clearAuthSession()` → removes `medikiosk_token`/`medikiosk_user`) and `router.replace('/login')`.
  It renders only where a `onSignOut` handler is provided, so the patient kiosk is unaffected.
- **Files changed:** `frontend/src/components/kiosk/KioskHeader.tsx`, `frontend/src/app/doctor/page.tsx`,
  `frontend/src/app/admin/page.tsx`.
- **Browser:** Sign Out clears token + redirects on /doctor and /admin; patient kiosk has no such control
  (by design). **PASS.**

---

## 4. Group 3 — remaining issues (§6, small group + retest)

### BUG-006 (and SEC-6) — Honest AI provenance label (P3) — FIXED & VERIFIED
- **Root cause:** the `/chat` page and the `AIChatbotDrawer` hard-coded "NVIDIA Nemotron 3 Ultra"
  regardless of the engine actually used, while no key/local LLM was configured and the reply came from
  the deterministic fallback — misleading provenance for medical content.
- **Fix:**
  - Backend `llm_service.chat_completion` accepts `return_engine` and returns `(text, engine)` where
    `engine ∈ {"local","openrouter","deterministic_fallback"}` (OpenRouter with empty content now falls
    through to the fallback). `chat_router` calls it with `return_engine=True` and adds
    `"engine"`/`"model"` to the `/api/chat/message` response (`model` is only set for the real `openrouter`
    path).
  - Frontend `engineLabel()` maps the engine to honest text; the misleading strings were replaced in the
    floating button, the drawer/page header, the welcome message, and the loading indicator; each AI
    message now shows a per-message **Source:** caption. No page text names a commercial model unless it
    actually produced the output.
- **Files changed:** `backend/app/services/llm_service.py`, `backend/app/api/chat_router.py`,
  `backend/tests/test_chat_router.py` (mock now returns a tuple; asserts `engine`/`model`),
  `frontend/src/app/chat/page.tsx`, `frontend/src/components/common/AIChatbotDrawer.tsx`.
- **API verification (browser `fetch`):** `POST /api/chat/message` → `200`,
  `engine="deterministic_fallback"`, `model=null`.
- **Browser verification:** header shows "AI Clinical Assistant • Clinical AI Assistant"; after sending a
  message the reply caption reads **"Source: Deterministic clinical fallback (no LLM configured)"**;
  `document.body` contains **no** "NVIDIA"/"Nemotron" text; console clean.
- **Evidence:** DOM a11y snapshot + `evaluate_script` assertions (screenshot capture unavailable this run —
  native viewport hidden). **PASS.**

### BUG-009 — `/api/chat/prompts` fetched twice per load (P3) — FIXED & VERIFIED
- **Root cause:** React StrictMode dev double-effect re-ran the prompts fetch on the same
  `role`/`language` deps with no de-duplication.
- **Fix:** a `promptsFetchedKeyRef` guard skips the fetch when the same `${role}:${language}` key was
  already requested this session (resets on failure so it can retry); applied in both the page and drawer.
- **Browser verification:** after a reload, network shows **exactly one** `GET /api/chat/prompts?...`
  request (previously two). **PASS.**

### BUG-007 — Branded 404 (P3) — FIXED & VERIFIED
- **Fix:** new `frontend/src/app/not-found.tsx` — MediKiosk-branded dark theme, "404 / Page not found",
  reassuring copy, and role-appropriate navigation (Kiosk Home, AI Assistant, Staff Login).
- **Files changed:** `frontend/src/app/not-found.tsx` (new).
- **Browser verification:** visiting `/this-route-does-not-exist` renders the branded page with the three
  navigation links (snapshot `uid` tree confirms), replacing the previous unstyled default. **PASS.**

### BUG-008 — Kiosk step does not update the URL (P3) — FIXED & VERIFIED
- **Fix:** root `frontend/src/app/page.tsx` now mirrors the intake wizard's deep-link pattern — a
  post-mount `router.replace` effect syncs `?view=<step>` for the patient wizard (physician/admin live on
  their own guarded routes and are excluded), and a mount effect restores the step from `?view=` on a
  refresh/bookmark. The sync effect is state-driven (not URL-driven), so it cannot loop.
- **Browser verification:** clicking "Start Patient Check-in" → URL becomes `/?view=language`;
  continuing → `/?view=patient_ident`; reloading at `/?view=patient_ident` restores the Patient-ID step
  (landing is not shown). **PASS.**

### BUG-010 — Register selects unvalidated / native-HTML5 reliance (P3) — FIXED & VERIFIED
- **Root cause:** the patient register fields relied solely on native browser validation, which is
  inconsistent on kiosk browsers / assistive tech; the Gender/Department selects carried no explicit,
  styled messaging.
- **Fix:** `/login` patient-register path uses explicit, styled validation: the `<form>` is `noValidate`
  so React controls messaging; a `validatePatientRegister()` layer checks Full name / Age (1–120) /
  Gender / Department and renders rose inline messages with red borders and `aria-invalid`; the selects
  now carry a real `required` + empty placeholder option. Staff login (identifier/password) received the
  same explicit treatment for consistency. Server-side validation remains the backstop (unchanged).
- **Files changed:** `frontend/src/app/login/page.tsx`.
- **Browser verification:** with all four patient fields cleared and submit clicked, **no native bubble**
  appears; four styled messages render ("Full name is required", "Enter a valid age between 1 and 120",
  "Please select a gender", "Please select an OPD department") and `aria-invalid` is set on 4 elements.
  **PASS.**

---

## 5. Final regression after Group 3 (§5)

| Check | Command | Result | Exit code |
|---|---|---|---|
| Full backend suite | `pytest -q` | **213 passed, 1 skipped** | **0** |
| Types | `npx tsc --noEmit` | no type errors | **0** |
| Production build | `next build` (dev stopped first, then restored) | ✓ Compiled successfully, **9 routes** incl. `/_not-found` | **0** |
| Browser (Group 3) | BUG-006 / 007 / 008 / 009 / 010 | all PASS (DOM/network/console) | — |
| Role-based access | DOCTOR/ADMIN/NURSE/anonymous re-checked via guard + API | unchanged, still enforced | — |

The single skipped test is pre-existing (an optional integration path) and was skipped before and after
this work.

---

## 6. Bug ledger — fixed / unresolved / blocked

| ID | Title | Severity | Status |
|---|---|---|---|
| BUG-001 | On-demand summary HTTP 500 | P2 | **Fixed + verified** |
| BUG-002 | Consent pre-checked, no decline | P1 | **Fixed + verified** |
| BUG-003 | No doctor/admin route guard, silent 401/403 | P1 | **Fixed + verified** |
| BUG-004 | Intake answers lost on Back | P2 | **Fixed + verified** |
| BUG-005 | Admin 403 silently swallowed | P2 | **Fixed + verified** |
| BUG-006 / SEC-6 | Misleading "NVIDIA Nemotron" label | P3 | **Fixed + verified** |
| BUG-007 | Unstyled builtin 404 | P3 | **Fixed + verified** |
| BUG-008 | Kiosk steps don't update URL | P3 | **Fixed + verified** |
| BUG-009 | Chat prompts fetched twice | P3 | **Fixed + verified** |
| BUG-010 | Register selects unvalidated / native-only | P3 | **Fixed + verified** |
| BUG-011 / SEC-2 | No logout anywhere | P3→P2 | **Fixed + verified** |

**Unresolved / not in scope of this fix set (from the audit's non-bug recommendations):**
- SEC-4 (demo quick-fill credentials on the login page) — left in place; the audit recommends gating them
  behind an explicit "demo mode" flag and removing them from public builds. Not fixed here to keep changes
  minimal and avoid altering seeded demo convenience; **flagged**.
- Responsive breakpoints on a real physical device (320/768/1024/1440 px) — **could not be verified** (the
  automation viewport is fixed; scripted resize is a no-op). Still unverified, not "passed".
- The ~921 pytest warnings (mostly `datetime.utcnow()` deprecation + environment warnings) and the
  docs/README claims audit — **not addressed** (out of the confirmed-bug scope).

---

## 7. Remaining security / reliability risks & notes

- **Provenance honesty is now correct, but the fallback is not a real diagnosis engine.** With no LLM
  configured, chat/summary output is a deterministic template. The UI now says so; clinical staff must still
  treat it as triage assistance, never autonomous diagnosis (unchanged by these fixes).
- **Client-side guards are UX hardening, not the security boundary.** `/doctor` and `/admin` are protected
  by `RequireAuth`, but the real enforcement remains server-side RBAC via `/api/auth/me` + role checks.
  The guard never trusts a client-forged role (verified: forged ADMIN token → server 401 → session cleared).
- **Auth token storage is `localStorage`** (pre-existing design). It is clearable via the new Sign Out but
  remains XSS-sensitive as before; no change was made to the storage mechanism in this pass.
- **Session termination is client-side.** `clearAuthSession()` removes the token; the backend has no
  revocation/list endpoint, so a stolen bearer token stays valid until expiry. Recommended follow-up
  (not implemented — would need a backend endpoint).
- **`.next` / OneDrive friction** can recur for the production build; the safe sequence (stop dev → build →
  restart dev) was used and is the reliable workaround.

---

## 8. Test-data and artifact inventory (for your approval before cleanup)

All rows created during this effort are **synthetic QA data only**. Nothing was deleted from the database,
and no QA records were removed. QA artifacts created/used live under `scratch/`:
- Screenshots: `scratch/p9_*.png` (Group 1/2 evidence).
- HTTP probe scripts: `scratch/p9_consent_check.ps1`, `scratch/p9_llm_summary_check.ps1`,
  `scratch/p9_dossier_check.ps1`.
- Pre-existing audit leftovers still present from the audit itself: `scratch/qa_*.ps1`, `scratch/qa_*.json`,
  `scratch/qa_big.wav`, `scratch/qa_dummy.txt`, `scratch/qa_empty.png`, and synthetic patients
  "QA Probe One/Two/Three" / "Browser QA Patient" (OPD-188).

> **No cleanup was performed.** I will **wait for your explicit approval** before deleting any database
> rows, scratch files, or QA artifacts.

---

## 9. Summary of what was genuinely fixed and verified

- All **three priority bugs (BUG-002, BUG-003, BUG-001)** are fixed and verified through automated tests
  **and** real browser workflows, with backend responses and persisted state confirmed.
- All **remaining confirmed bugs** were fixed and verified in two groups:
  - Group 2: BUG-004, BUG-005, BUG-011/SEC-2.
  - Group 3: BUG-006/SEC-6, BUG-007, BUG-008, BUG-009, BUG-010.
- Final regression is green: full backend suite **213 passed / 1 skipped (exit 0)**,
  `tsc --noEmit` **exit 0**, production build **exit 0 (9 routes)**.
- **Safety requirements honored:** the database was never reset/migrated/deleted; only synthetic test data
  was used; no PHI/credentials/tokens/secrets are reproduced in this report; no QA records/scratch files
  were removed; no dependencies were installed; no signed encounter or verified clinical information was
  overwritten; no red-flag rule was changed; code changes were kept minimal; `npm run build` was never run
  concurrently with `next dev`.
- **Honest limitations:** Group 3 screenshots could not be captured (native browser viewport unavailable) —
  those fixes are evidenced by DOM/a11y snapshots, network request counts, console state, and live API
  responses rather than images. Real-device responsive testing, SEC-4 demo-credential gating, and the
  pytest-warning/docs cleanup remain open items and were **not** marked as passing.
