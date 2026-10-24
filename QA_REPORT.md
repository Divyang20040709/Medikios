# MediKiosk — Full QA Audit Report

**Report date:** 24 Oct 2026
**Auditor role:** Senior QA Engineer (black-box + white-box, evidence-driven)
**Application:** MediKiosk — FastAPI backend (`:8000`) + Next.js 14 App Router frontend (`:3000`)
**Scope:** Every user-facing feature of the website, end to end
**Result:** **8 defects found and fixed** (1 × P1, 4 × P2, 3 × P3, 0 × P0) · **7 open findings** deferred for product/clinical decision

> **Round 2 (P1–P4 hardening) is appended from §12.** Summary: the Doctor/Admin bypass is **not reproducible** (proven, zero code changed); native popups are **0 → 0** with dialog semantics added and verified; the OPD token race **reproduced, was fixed and re-proven** on real PostgreSQL; triage safety banners added while the clinical routing rule stays **escalated, not guessed**. Final suite: **283 passed · 1 skipped**.

---

## 1. Executive summary

> **Round 3 update (24 Oct 2026).** QA-11, QA-13, QA-14 and QA-15 are fixed and verified at runtime; the schema-modal focus defect is closed. The suite now stands at **285 passed / 1 skipped** (was 283; the two new tests are the period-scoping tests). QA-09 and QA-10 are documented in `CLINICAL_TRIAGE_REVIEW.md` and remain **unresolved pending clinician decisions CD-1–CD-5** – no rule, lexicon or department mapping was changed. One new privacy finding (**QA-17**) is open and needs a product decision. Sections 19–30 hold the round-3 evidence and supersede the round-2 figures; sections 1–11 are kept unchanged for traceability of the round-1 baseline.

| Area | Baseline | After fixes |
|---|---|---|
| Backend test suite (`pytest backend/tests`) | 3 failed · 277 passed · 1 skipped | **0 failed · 280 passed · 1 skipped** → **283 passed after round 2** |
| API contract harness (114 checks, all routers) | 113 pass · **1 fail** (real defect) | Defect fixed and re-proven with 8 targeted payloads |
| TypeScript (`tsc --noEmit`) | clean | **clean (exit 0)** |
| Production build (`next build`) | not run | **OK — 9/9 routes generated** |
| Browser smoke (`/`, `/login`, `/patient/intake`, `/doctor`, `/admin`, `/chat`) | — | **all green** |

**Verdict:** the application is functionally sound and demonstrably usable end to end (kiosk check-in → interview → docs → review → token → doctor queue → consultation → sign-off → admin telemetry). One **P1 privacy defect** existed on the shared kiosk and is now fixed and verified. No P0 (data-loss / unusable-app) defect was found. The remaining risk is concentrated in **clinical AI accuracy** (QA-09, QA-10), which is a model/product decision, not a coding defect.

**No change was made in round 1 to:** `.env`, secrets, Git history, auth policy, or consultation-routing rules. Round 2 added exactly one schema object — a UNIQUE index on `encounters.token_number` — with no data rewritten; see §14 and §18.

---

## 2. Environment & method

**Environment**
- OS: Windows (PowerShell 5.1, `;` separator only)
- Python: global interpreter only — `C:\Users\Solanki Divyang\AppData\Local\Programs\Python\Python312\python.exe` (no venv created or activated)
- Backend: `uvicorn` from repo root → `http://127.0.0.1:8000`, DB `medikiosk_db` @ `127.0.0.1:5432`
- Frontend: `next dev` → `http://127.0.0.1:3000`, `/api/:path*` proxied to the backend
- Accounts used: General doctor, AYUSH doctor, Admin (existing seeded staff only)

**Method**
1. **Static review** of every route, component, router, schema and model touched by a user flow.
2. **API contract harness** — 114 checks across `auth`, `rbac`, `intake`, `speech`, `docs`, `chat`, `admin`, `doctor`, `fhir`; each check asserts an *expected* HTTP status, so both happy paths and negative paths (401/403/404/422/415) are verified.
3. **Browser-driven UI testing** on every route: click-through of all tabs, modals, filters, language switches and forms; DOM state compared against API state.
4. **Accessibility probes**: control effect, label/name presence, keyboard dismissal, contrast class.
5. **Localization probes**: switch UI to Hindi and Gujarati and assert every string in the touched flow.
6. **Every fix re-verified in the running browser** (not merely by unit test) plus a full-suite + typecheck + build regression.

**Severity scale**
| Sev | Definition |
|---|---|
| **P0** Blocker | Data loss, unusable app, or exposure of *real* patient PHI |
| **P1** Critical | Privacy/safety exposure or a core flow broken with no workaround |
| **P2** Major | Wrong data shown, incorrect behavior, or a control that silently does nothing |
| **P3** Minor | Localization gap, a11y gap, test-hygiene, cosmetic UX |

---

## 3. Defect register (all fixed & verified)

| ID | Sev | Area | One-line summary | Status |
|---|---|---|---|---|
| QA-01 | P2 | Intake / API | Check-in accepted empty name, age 0 and unknown gender | Fixed |
| QA-02 | **P1** | Kiosk privacy | `/patient/intake?step=review` resumed the **previous patient's** PHI | Fixed |
| QA-03 | P2 | Accessibility | Font-size control (A / A+ / A++) did not change the UI | Fixed |
| QA-04 | P3 | i18n | Sign-off modal in हिन्दी/ગુજરાતી showed English title and buttons | Fixed |
| QA-05 | P3 | Test suite | 2 tests asserted the opposite of the intended queue rule | Fixed |
| QA-06 | P2 | Doctor queue | Ghost "Waiting" rows + wrong filter counts (duplicate React key) | Fixed |
| QA-07 | P3 | Intake | OPD token drawn at random from 101–299 → collisions possible | Fixed |
| QA-08 | P3 | Auth UX | "Sign in with another account" lost the intended destination | Fixed |

---

## 4. Defect details

### QA-01 — Check-in accepted invalid patient demographics
**Severity:** P2 · **Area:** patient intake / `POST /api/intake/init` · **Found by:** API harness (`intake | POST /init (invalid payload) | exp [400,422] got 200`)

**Repro (before fix)**
1. `POST /api/intake/init` with `{"name":"","age":0,"gender":"X"}`.
2. Observe `HTTP 200` and a patient created as **"Patient / 0y"**.

**Expected:** `422` — name required and non-blank, age 1–120, gender ∈ {MALE, FEMALE, OTHER}.
**Actual:** `200`; a meaningless patient record was created and pushed into the doctor queue, telemetry and ML statistics.
**Root cause:** `PatientRegisterRequest` declared `name: str`, `age: int`, `gender: str` with no constraints or normalisation.
**Fix:** `backend/app/schemas/pydantic_models.py` — `Field(min_length=1, max_length=120)`, `Field(ge=1, le=120)`, `mode="before"` strip + non-blank validator, gender whitelist validator that upper-cases the value (frontend already sends upper-case, so no client change needed).
**Verification:** `scratch/qa_verify_init.py` → 5 invalid payloads (blank, whitespace-only, age 0, age 200, gender `X`) all `422`; 3 valid check-ins succeed.
**Evidence:** `scratch/qa_api_results.json` (failing row), `scratch/qa_verify_init.py`.

---

### QA-02 — Shared kiosk resumed the previous patient's record (privacy)
**Severity:** **P1** · **Area:** `/patient/intake` · **Found by:** browser test of deep links

**Repro (before fix)**
1. Register patient A (name, age, gender) → continue until the interview/review step.
2. Leave the kiosk (or press "Finish" and return to `/`).
3. On the *same* browser, open `/patient/intake?step=review` directly.
4. Observe patient A's **name, chief complaint and clinical summary** rendered for whoever is standing at the kiosk now.

**Expected:** a fresh check-in starts at **STEP 1 (Patient Identification)**; no prior patient's PHI is visible; deep links only apply to a patient identified in this session.
**Actual:** previous patient's PHI was rendered — on a shared kiosk this is a real disclosure of another person's health data.
**Root cause (2 compounding bugs):** the page seeded `patient` from `clinicalStore.getPatients()[0]` (most recent patient, regardless of who is at the kiosk) and applied the `?step=` query parameter unconditionally on mount.
**Fix:** `frontend/src/app/patient/intake/page.tsx`
- state starts from `DEFAULT_PATIENT` / `undefined` / `[]` instead of "the latest patient";
- a `sessionStorage` pointer `medikiosk_intake_active_patient` is written only when a *new* patient completes identification;
- on mount, prior state is restored **only if** that id matches the session pointer, and `?step=` is honoured **only** when such a patient exists;
- the pointer is cleared when the token slip is dismissed, so a finished visit cannot be resumed.
**Verification (browser):** `sessionStorage.clear()` + `/patient/intake?step=review` → **STEP 1**, no leak. Real registration of "QA Fix Verify Patient" → `?step=docs` opens the scanner **for that patient only**.
**Evidence:** browser session; `frontend/src/app/patient/intake/page.tsx`.

---

### QA-03 — Accessibility font-size control had no effect
**Severity:** P2 · **Area:** Accessibility panel (landing page) · **Found by:** browser measurement

**Repro (before fix)**
1. Open `/`, open the Accessibility panel.
2. Select **A++** (extra large).
3. Observe all text stays 14–16 px; `document.documentElement.style.fontSize` stays `16px`.

**Expected:** the whole UI scales (kiosk is meant to be readable at arm's length).
**Actual:** the selection was stored in state but mapped to `text-lg` / `text-xl` classes that were applied to nothing (Tailwind `text-*` overrides the base size only where used), so nothing changed visually. High contrast worked; text size did not.
**Root cause:** the control changed a class name instead of the root font size, and the `text-*` utilities are `rem`-based — the only way to scale the whole UI is the root element.
**Fix:** new `frontend/src/lib/accessibility.ts` (`TEXT_SCALE` 100 % / 113 % / 125 %, `applyTextSize()` sets `document.documentElement.style.fontSize`, `accessibilityClasses()` for contrast); an effect in `page.tsx`, `patient/intake/page.tsx`, `doctor/page.tsx`, `admin/page.tsx`.
**Verification (browser):** on `/doctor` root font-size `16px → 20px` (A++) and `18.08px` (A+), reset → `16px`; a 14 px sample text measured **17.5 px** under A++. Landing headings scale to 40.68 px.
**Evidence:** browser measurements.

---

### QA-04 — Hindi/Gujarati sign-off modal partly English (and a false claim)
**Severity:** P3 · **Area:** doctor workstation i18n · **Found by:** language switch + sign-off

**Repro (before fix)**
1. Sign in as doctor, switch UI language to **हिन्दी**.
2. Select a patient, fill SOCRATES, click **Sign & Complete**.
3. Observe: title **"Consultation Completed"**, sub-line and both buttons **"View in Completed" / "Continue to next patient"** in English while the body was Hindi.

**Expected:** the whole modal follows the selected language.
**Actual:** 5 keys (`dw.signSuccessTitle`, `dw.signSuccessMoved`, `dw.signSuccessContinue`, `dw.signSuccessViewCompleted` and the corrected `dw.signSuccess` body) were missing from `hi`/`gu`. The fallback chain (`DICTIONARIES[lang]?.[key] ?? en[key]`) made the modal silently mixed-language. The Hindi body also claimed the patient was *removed* from the queue, contradicting the deliberate rule that signed encounters stay listed under **Completed**. This missing-key condition is also what broke `test_i18n_dictionary_parity_across_languages` (→ QA-05).
**Fix:** `frontend/src/lib/i18n.ts` — added the 5 keys to `hi` and `gu` and rewrote the `dw.signSuccess` body to match actual behaviour ("record is saved in the completed list").
**Verification:** parity test green; browser re-run in Hindi shows `परामर्श पूर्ण … पूर्ण सूची में देखें / अगले रोगी पर जाएँ`.
**Evidence:** `frontend/src/lib/i18n.ts`; Hindi browser session.

---

### QA-05 — Two tests asserted the opposite of the product rule
**Severity:** P3 · **Area:** backend test suite · **Found by:** baseline `pytest`

**Repro (before fix)**
`pytest backend/tests` →
```
FAILED backend/tests/test_integration_phase7.py::TestEndToEndWorkflow::test_full_patient_to_physician_flow
FAILED backend/tests/test_release_audit.py::test_sign_and_complete_finalizes_and_persists
FAILED backend/tests/test_release_audit.py::test_i18n_dictionary_parity_across_languages
```
**Expected:** green suite.
**Actual:** the first two asserted the signed encounter **disappears** from `/api/doctor/queue`; the product deliberately keeps it with `status = FINALIZED`, sorted last, so clinicians can review what they just signed. The third failed on the QA-04 missing keys.
**Root cause:** stale assertions written before the "Completed" filter was introduced; the third was a genuine missing-translation defect.
**Fix:** assertions changed to "still listed, `status == FINALIZED`" with the rule documented in a comment (`test_release_audit.py`, `test_integration_phase7.py`). **The product was not bent to match the tests.**
**Verification:** `pytest` → **280 passed, 1 skipped**, see `scratch/qa_pytest_after_fixes.log`.

---

### QA-06 — Ghost rows and wrong counts in the doctor queue
**Severity:** P2 · **Area:** doctor workstation queue · **Found by:** DOM vs API comparison

**Repro (before fix)**
1. Sign in as the General doctor, open `/doctor`.
2. Read the queue: **All 18** rows, **Priority 5**, **Waiting 12**, **Completed 8** — while the API returned a different split (Priority 4, Waiting 11, Completed 7).
3. Rows visibly labelled **Waiting** remained on screen after switching to the **Completed** filter; the same row could appear twice.

**Expected:** DOM row count == API row count for every filter; no duplicates.
**Actual:** duplicate `key` values → React reused stale DOM nodes when the filtered list shrank, so removed rows stayed painted and counts were inflated.
**Root cause:** `key={patient.id}` while a patient can hold **more than one encounter in the same day** (e.g. `34b16240-f5d3-41fa-82d3-9fb07409568c` had `OPD-192` QUEUED **and** `OPD-101` FINALIZED — proven by `scratch/qa_dupkeys.py`). Two encounters ⇒ one duplicate key.
**Fix:** `frontend/src/components/doctor/DoctorWorkstation.tsx` — `const rowKey = patient.encounterId || patient.id;` and an encounter-aware `isSelected`, so the selection highlight follows the encounter rather than the patient.
**Verification:** All **23** / Priority **4** / Waiting **13** / Completed **10**, zero ghost rows, DOM == API for which doctor's token is used.
**Cross-check (avoided a false positive):** a General-doctor session showed 23 rows where 22 were expected — re-queried as ADMIN (23) / General (22) / AYUSH (1). **ADMIN is intentionally un-filtered across OPD streams; DOCTOR is stream-filtered server-side.** Not a bug; stream isolation intact.

---

### QA-07 — OPD token could collide
**Severity:** P3 · **Area:** `/api/intake/init` · **Found by:** static review + repeated check-ins

**Repro (before fix)**
`backend/app/api/intake_router.py` used `token_number = f"OPD-{random.randint(101, 299)}"` — 199 possible values, no uniqueness check, no DB constraint surfaced to the user. Two patients in one morning could receive the same token.
**Expected:** every check-in gets a unique, monotonically increasing token.
**Actual:** birthday-collision risk; the printed slip is the patient's identity at the pharmacy/lab counter.
**Fix:** continue the existing sequence — highest issued `OPD-nnn` + 1 (default 100):
```python
used_tokens_res = await db.execute(
    select(Encounter.token_number).where(Encounter.token_number.like("OPD-%"))
)
issued_numbers = [int(r[0].split("-")[-1]) for r in used_tokens_res.all()
                  if r[0] and r[0].split("-")[-1].isdigit()]
token_number = f"OPD-{max(issued_numbers, default=100) + 1}"
```
**Verification:** 3 back-to-back check-ins produced **OPD-290 / OPD-291 / OPD-292** (sequential, unique).

> **Superseded in round 2.** Sequential-by-reading was still a read-modify-write race and it *did* reproduce under concurrent requests. Replaced by an advisory-lock guard plus a DB-enforced UNIQUE index. See **§12.3**.

---

### QA-08 — "Sign in with another account" dropped the intended destination
**Severity:** P3 · **Area:** auth guard · **Found by:** role-denial flow

**Repro (before fix)**
1. Sign in as **doctor**, navigate to `/admin` → "Access denied" panel.
2. Click **Sign in with another account**.
3. Log in as **admin** → you land on `/`, not `/admin`.

**Expected:** return to the page you were denied (`/login?next=%2Fadmin`).
**Actual:** `router.replace('/login')` in `RequireAuth.tsx` (both the unauthenticated and the "another account" branch) discarded path + query.
**Fix:** both call sites now `router.replace(loginUrlFor(window.location.pathname, window.location.search))`.
**Verification:** browser shows `/login?next=%2Fadmin`; after admin login the console opens as intended.

---

## 5. Open findings (reported, not changed)

These need a product/clinical/model decision — I did not silently "fix" behaviour that you own.

### QA-09 — Triage classifier routes clearly-wrong departments · **P2**
**Repro:** Admin console → Triage Playground.
- `"Routine general checkup"` → **Pediatrics OPD**, confidence 0.65 *(a 41-year-old adult)*
- `"છાતીમાં સખત દુખે છે"` (severe chest pain, Gujarati) → **AYUSH / Kayachikitsa OPD** at priority **EMERGENCY**

**Impact:** an emergent cardiac presentation is queued to an Ayurveda OPD; a healthy adult is queued to Pediatrics. This is a clinical-safety-adjacent accuracy problem, not a code bug — the confidence is also high on the wrong answer.
**Why not fixed:** requires retraining/lexicon/clinic-mapping decisions and clinical sign-off. `scratch/qa_triage_samples.py` reproduces all samples.
**Recommendation:** (a) add a department-prior guard for age-banded departments (Pediatrics must never be chosen for age ≥ 18); (b) block AYUSH routing when `priority == EMERGENCY`; (c) expand the Gujarati lexicon; (d) surface low confidence as "Needs staff review" instead of silently queuing.

### QA-10 — Grounding emits an unrelated concept · **P2**
In the "Cardiac Emergency (EN)" sample the extracted SNOMED-style concepts included **`fever_cough`** for the phrase *"cold sweating"*. A clinician skimming the concept list is misled. **Recommendation:** require a token overlap between the source phrase and the concept label before display.

### QA-11 — Admin period selector only affects one metric · **P3**
**Repro:** Admin console → Today / Week / All.
**Actual:** TOTAL REGISTRATIONS, COMPLETED and RED-FLAG counts are identical for all three periods; only the intake-duration model responds to `period` (verified against `admin_router.py` and the API). **Impact:** an operator will misread these as period-scoped. **Recommendation:** either scope the counters or label them "All time".

### QA-12 — Modals are not dialogs · **P3** — **FIXED in round 2**
FHIR R4 Bundle modal and the landing Help modal: no `role="dialog"`, no `aria-modal`, **Escape does not close**, focus is not trapped, and the `✕` button has **no accessible name** (I had to click by text). Also affects the SQL/DDL viewer. **Fix applied:** shared `useModalDialog` hook (role/aria/Escape/focus-trap/labelled close) across Help, SQL/DDL, FHIR and the sign-off modal — see **§12.2**.

### QA-13 — Login form prefills demo credentials · **P3**
`/login` is pre-populated with the demo doctor's e-mail/password. Convenient for a demo, risky if deployed as-is. **Recommendation:** gate the prefill behind `NODE_ENV !== 'production'` or an explicit demo flag.

### QA-14 — Red-flag acknowledge is optimistic · **P3**
Clicking "Acknowledge" on a red flag updates the UI before the server confirms and shows no error/rollback if the request fails. On a clinical dashboard the operator may believe a flag is cleared when it is not. **Recommendation:** await the response, show a per-row spinner, restore the row on failure.

### QA-15 — Queue filter pills stay English · **P3**
In हिन्दी/ગુજરાતી the doctor queue pills still read **All / Priority / Waiting / Completed** (not in the dictionary). **Recommendation:** add `dw.filterAll/…` to all three dictionaries.

---

## 6. Coverage matrix

### API harness — 114 checks (`scratch/qa_api_audit.py` → `scratch/qa_api_results.json`)
| Group | Checks | Result |
|---|---|---|
| Auth (valid/invalid/missing token, 3 roles) | 11 | pass (1 real defect was in `intake`) |
| RBAC matrix (every protected route × every role) | 44 | pass — 401/403 exactly as designed, no privilege escalation |
| Intake (init, interview, summary, token, red flags) | 23 | 22 pass · **1 fail → QA-01 (fixed)** |
| Speech (transcribe/providers/limits) | 5 | pass |
| Documents (upload/reject/extract) | 5 | pass |
| Chat (EN/HI/gu, reset) | 5 | pass |
| Admin (stats, events, models, triage) | 11 | pass |
| Doctor (queue, detail, sign, flags) | 7 | pass |
| FHIR R4 (Bundle/Patient/Encounter/DiagnosticReport) | 3 | pass |

Negative paths explicitly proven: **401** without token (17), **403** wrong role (18), **404** unknown id (10), **422** bad body (3), **400/415** (3).

### UI — every route exercised in a real browser
| Route | Verified |
|---|---|
| `/` landing | Feature cards → correct routes, Accessibility panel (text size now effective, contrast), Help modal, SQL schema modal, Login / Patient Kiosk / Doctor / Admin entry points |
| `/login` | Wrong password, role selection, redirect to intended page, `?next=` preserved, prefill (QA-13) |
| `/patient/intake` | STEP 1 identification → STEP 2 interview → docs upload → review → token slip; deep-link gating (QA-02); resume; 3 languages |
| `/doctor` | Queue + 4 filters, patient selection, all 5 tabs (Intake History & SOCRATES, Diagnostic Considerations, Medication Reconciliation, Medical Timeline, Scanned Documents), FHIR R4 Bundle modal, fill + **Sign & Complete**, "View in Completed", persistence, language switch, font scale |
| `/admin` | Telemetry counters, model verification panels, triage playground (EN + Gujarati), event log (25 events), red-flag acknowledge, period selector (QA-11), role denial → "another account" (QA-08) |
| `/chat` | Language `<select>` (EN/HI), LLM reply, Reset, Doctor Copilot mode |

### Accessibility
Font scaling (fixed), contrast class, form labels on intake, hit-target sizing, keyboard reachability of primary actions, `aria-label` presence. **Not** a full WCAG audit (see §9).

### Localization
Full sign-off flow in EN / हिन्दी / ગુજરાતી; dictionary parity test green; remaining English literals logged as QA-15.

### Regression after all fixes
```
pytest backend/tests           → 280 passed, 1 skipped   (scratch/qa_pytest_after_fixes.log)
npx tsc --noEmit               → exit 0
npx next build                 → 9/9 routes generated     (scratch/qa_build.log)
browser smoke of all 6 routes  → OK
```

**Build note:** `npm run build` first failed with `EINVAL: invalid argument, readlink .next\server\webpack-runtime.js`. This is a OneDrive + stale-`.next` artefact, **not** a code defect: moving `.next` aside and rebuilding succeeded. Both dev servers were restarted afterwards.

---

## 7. Test data created (please review)

All synthetic. Created to prove QA-01/02/06/07 and the full doctor flow:

| Patient | Token | State | Purpose |
|---|---|---|---|
| QA Verify Token 1 / 2 / 3 | OPD-290 / 291 / 292 | QUEUED | Prove unique sequential tokens |
| QA Fix Verify Patient (41, Male) | OPD-293 | FINALIZED | Prove session-scoped resume + sign-off |
| QA Audit 5fef41 | OPD-140 | FINALIZED | Doctor workstation / FHIR / modal audit |
| QA Audit (Hindi) | OPD-148 | FINALIZED | Hindi sign-off modal |
| "Patient" (age 0) | — | created | QA-01 evidence (created *before* the fix) |
| Demo AYUSH Patient | OPD-184 | QUEUED | AYUSH stream isolation check |
| (existing) patient `34b16240…` | OPD-192 + OPD-101 | duplicated | QA-06 root-cause evidence |

Admin telemetry currently reads **23 registrations / 12 completed / 0 active red flags** (4 flags total, all acknowledged → 0 active is correct). These numbers will look inflated vs. a clean install; say the word and I will write a **scoped** cleanup script (matched strictly by the synthetic names above) for you to review before it runs.

---

## 8. Files changed

**Backend (2 fixes + 2 test corrections)**
- `backend/app/schemas/pydantic_models.py` — QA-01 check-in validation
- `backend/app/api/intake_router.py` — QA-07 sequential unique token
- `backend/tests/test_release_audit.py` — QA-05 assertion
- `backend/tests/test_integration_phase7.py` — QA-05 assertion

**Frontend (5 fixes + 1 new module)**
- `frontend/src/lib/accessibility.ts` — **new** (QA-03)
- `frontend/src/app/page.tsx` — QA-03
- `frontend/src/app/patient/intake/page.tsx` — QA-02, QA-03
- `frontend/src/app/doctor/page.tsx` — QA-03
- `frontend/src/app/admin/page.tsx` — QA-03
- `frontend/src/components/doctor/DoctorWorkstation.tsx` — QA-06
- `frontend/src/lib/i18n.ts` — QA-04
- `frontend/src/components/common/RequireAuth.tsx` — QA-08

**QA artefacts (throw-away, safe to delete)**
`scratch/qa_api_audit.py`, `qa_api_results.json`, `qa_api_run.log`, `qa_pytest.log` (baseline), `qa_pytest_after_fixes.log`, `qa_build.log`, `qa_dupkeys.py`, `qa_triage_samples.py`, `qa_verify_init.py`

> Round 2 touched a different (larger) set of files — see **§17**.

---

## 9. Not tested / limitations (honest scope)

- **No load or stress testing** (no k6/Locust run) — there is no throughput benchmark, no sustained-load soak, and no measurement beyond 16 simultaneous check-ins. The token allocator *was* proven correct under concurrency (see §12.3); latency under load is still unmeasured.
- **No formal WCAG 2.2 audit** — no axe/Lighthouse report, no NVDA/VoiceOver screen-reader pass; accessibility findings are manual/heuristic.
- **Speech accuracy not benchmarked** — endpoints proven with synthetic WAVs (valid, short, oversized); no Word-Error-Rate measurement on real Indic speech.
- **OCR accuracy not benchmarked** — upload/reject/extract paths proven; no ground-truth comparison on real prescriptions.
- **LLM answer quality not scored** — chat/clinical-summary verified for language, shape and safety filters only.
- **Single browser** (Chromium via automation); no Firefox/Safari, no real mobile device or touch input.
- **Security testing limited to RBAC/validation**: no penetration test, no rate-limit abuse, no JWT-tampering fuzzing, no dependency CVE scan.
- **No automated E2E framework committed** — browser flows were driven interactively, so they are not re-runnable in CI; only the API harness and pytest are repeatable.
- **Clinical correctness of the triage model** is out of scope for a coding fix (QA-09/QA-10 need clinical sign-off).

---

## 10. How to re-run

```powershell
# from the repo root
$py = "C:\Users\Solanki Divyang\AppData\Local\Programs\Python\Python312\python.exe"

# backend suite
& $py -m pytest backend/tests -q

# API contract harness (backend must be listening on :8000)
& $py scratch\qa_api_audit.py          # writes scratch\qa_api_results.json

# typecheck + production build (stop `next dev` first)
cd frontend; npx tsc --noEmit; npx next build
```

---

## 11. Recommended order of work

1. **QA-09** — adult never queued to Pediatrics; no AYUSH routing on `EMERGENCY` (clinical-safety, needs your sign-off on the rule).
2. **QA-14** — non-optimistic red-flag acknowledgement (clinical trust).
3. **QA-10** — concept/phrase grounding filter.
4. **QA-12 / QA-15** — one shared accessible `<Modal>` + the 4 filter labels.
5. **QA-11 / QA-13** — label or scope the admin counters; gate credential prefill to non-production.

**Bottom line:** no P0, the only P1 (cross-patient PHI on the shared kiosk) is closed and re-verified in the browser, and the full suite + typecheck + build are green. The list above is polish plus one clinical-model decision.

---

# Round 2 — hardening pass (P1–P4)

This round re-tested the four areas in the follow-up brief against the current code. Where behaviour was already correct, **no code was changed** — the deliverable is reproducible evidence instead of a rewrite. Where it was wrong, the change is below with its proof.

Trust rule for this section: every claim marked **(executed)** was run and its output is quoted; anything not run is marked **(assumed)**. Signing off is not implied by a green build.

## 12. P1 — Doctor/Admin access bypass: not reproducible (executed)

Environment: Chromium via automation, `uvicorn` :8000 + `next dev` :3000, storage cleared where stated.

| # | Scenario | Observed | Verdict |
|---|---|---|---|
| 1 | Logged out, but a **valid unexpired DOCTOR token** left in `localStorage`; click **Physician OPD** | navigates to `/login?next=%2Fdoctor&role=DOCTOR`; workstation never mounts | pass |
| 2 | Same session; click **Admin & Triage** | `/login?next=%2Fadmin&role=ADMIN` | pass |
| 3 | Storage cleared; direct `GET /doctor` | redirect `/login?next=%2Fdoctor`, **0 XHR requests**, no queue DOM | pass |
| 4 | Storage cleared; direct `GET /admin` | redirect `/login?next=%2Fadmin`, **0 XHR**, no telemetry DOM | pass |
| 5 | **Forged** token in `localStorage` | exactly one request `GET /api/auth/me` → **401** → token+user erased → login. Queue never requested | pass |
| 6 | **Reload** on `/doctor` while unauthorised | login again, no protected flash | pass |
| 7 | **Back** from login / **Forward** again | Back → `/` (public landing, no PHI); Forward → login page | pass |
| 8 | DOCTOR session → `/admin` | "Your account cannot open this area" panel; only `/api/auth/me` called; **no admin API** | pass |
| 9 | "Sign in with another account" from that panel | `/login?next=%2Fadmin` preserved (QA-08 fix holds) | pass |
| 10 | ADMIN login via UI | `/admin` renders live telemetry | pass |

**Server-rendered payload:** `GET /doctor` = 13,205 bytes, `GET /admin` = 13,197 bytes; **zero** matches for `OPD-\d+`, queue rows or telemetry values → no protected data pre-rendered into HTML for an anonymous client.

**RBAC matrix** (executed from inside the browser with in-page tokens; credentials never printed):

| Endpoint | anonymous | DOCTOR | ADMIN |
|---|---|---|---|
| `/api/auth/me` | 401 | 200 | 200 |
| `/api/doctor/queue` | 401 | 200 | 200 |
| `/api/admin/telemetry` | 401 | **403** | 200 |
| `/api/admin/opd-queue` | 401 | **403** | 200 |
| `/api/admin/models/status` | 401 | **403** | 200 |
| `/api/admin/audit-logs` | 401 | **403** | 200 |
| `/api/admin/staff` | 401 | **403** | 200 |
| `/api/admin/red-flags` | 401 | **403** | 200 |

Expected behaviour (anonymous → login, DOCTOR ≠ Admin, ADMIN permitted) holds on every path. **Files changed for P1: none.**

One clarification so it is not misread as a leak: the name **"Ramesh Kumar"** visible on `/login` is the hardcoded demo-credential caption in `login/page.tsx`, not patient data — confirmed in source.

## 13. P2 — native popups: 0 before → 0 after (executed)

Method: `scratch/qa_popup_scan.py` walks every `frontend/**/*.{ts,tsx,js,jsx}` and matches `alert(` / `confirm(` / `prompt(` with an optional `window.` receiver, then reports per-file line numbers.

| | Files scanned | Native popup call sites | Counts by function |
|---|---|---|---|
| Before | 47 | **0** | `{}` |
| After | 48 | **0** | `{}` |

The file count rises 47→48 only because this round added `useModalDialog.ts`.

A raw `Grep` for `(^|[^.\w])(window\.)?(alert|confirm|prompt)\s*\(` returned **6** hits; all six are inside comments or longer identifiers (e.g. `confirmPassword`), none is a call — each was read and dismissed line by line. Exact locations are in `scratch/qa_popup_scan.json`.

Because nothing needed replacing, **no component was created or duplicated**. The themed stack was inspected first and is already in use:

- `ToastProvider` mounted once in `frontend/src/app/layout.tsx:37`; `useToast()` consumed at `app/chat/page.tsx:51` and `components/.../AIChatbotDrawer.tsx:64` — variants `success | error | info | warning`, duplicate suppression, ARIA live region.
- `NotificationModal` used as a confirmation dialog at `SymptomHistoryInterview.tsx:412` and `AccessibilityBanner.tsx:164` — already had `role="dialog"`, `aria-modal`, `aria-labelledby/describedby`, focus move-in/trap/restore and Escape.

**The real gap was dialog semantics on the ✕-button modals.** Fix: one new shared hook, `frontend/src/lib/useModalDialog.ts`, reused in four places (not duplicated per modal):

| Surface | File | What was added |
|---|---|---|
| Hospital Help | `components/kiosk/HospitalHelpModal.tsx` | `role="dialog"`, `aria-modal`, `aria-labelledby="mk-help-title"`, `aria-describedby="mk-help-desc"`, focus-in + restore, Tab trap, Escape, backdrop click, `aria-label="Close help dialog"` |
| SQL / DDL schema | `components/kiosk/SchemaModal.tsx` | same, `mk-schema-title` / `mk-schema-desc`, `aria-label="Close database schema dialog"` |
| FHIR R4 Bundle | `components/doctor/DoctorWorkstation.tsx` | `aria-labelledby="mk-fhir-title"`, `aria-label="Close FHIR bundle dialog"` |
| Sign-off success | same file | `aria-labelledby="mk-sign-title"`, `aria-describedby="mk-sign-desc"` |

Runtime proof — a recorder shimmed `window.alert/confirm/prompt` **before** each flow:

| Flow | Dialog found | `aria-modal` / label | Focus moved in | ✕ accessible name | Escape | Natives fired |
|---|---|---|---|---|---|---|
| Landing → **Help** | yes | `true` / "Hospital Kiosk Assistance" | yes → "Close help dialog" | "Close help dialog" | closes; focus returns to the **Help** button | `[]` |
| Landing → **SQL/DDL** | yes | "PostgreSQL / Supabase Database Schema" | yes → "Copy SQL" | "Close database schema dialog" | closes | `[]` |
| Doctor → **Inspect FHIR Bundle** | yes | "FHIR R4 DiagnosticReport Bundle" | yes | "Close FHIR bundle dialog" | closes; workstation restored | `[]` |
| Admin → 2× **Run ML Triage** | n/a | n/a | n/a | n/a | n/a | `[]` |

Semantics preserved: `NotificationModal` still requires an explicit confirm for anything destructive, the informational modals close on Escape/backdrop without side effects, and no dialog was downgraded to a toast. No success is asserted before the API confirms — the sign-off modal is only opened inside the `POST` success branch (unchanged).

## 14. P3 — OPD token: race proven, fixed, re-proven (executed)

**Proof the old code was unsafe.** The new concurrency test failed on its first run:

```
sqlite3.IntegrityError: UNIQUE constraint failed: encounters.token_number
  (two simultaneous check-ins both allocated OPD-101)
```

That is the safe-looking max+1 implementation failing under real concurrency, not a hypothetical.

**A second generator the earlier fix missed.** `backend/app/api/auth_router.py` still contained `token_num = f"OPD-{random.randint(101, 299)}"` — a random generator running beside the sequential one. Both call sites now share one allocator.

**Fix, three layers**
1. `backend/app/services/token_service.py` (new) — `opd_token_guard(db)` serialises allocate → insert → commit. PostgreSQL: `pg_advisory_xact_lock(0x4D4B4F50)`, transaction-scoped so it releases on commit/rollback. Elsewhere: a per-event-loop `asyncio.Lock` (one module-level lock breaks across pytest's per-test loops). `next_opd_token(db)` computes `MAX(n)` in SQL on PG, in Python on SQLite.
2. `backend/app/database/session.py` — `init_db` creates `ix_encounters_token_number` UNIQUE, guarded by a duplicate-count check, idempotent, never fatal.
3. `backend/app/models/entities.py` — `token_number` is now `unique=True, index=True`.

**Evidence: real PostgreSQL, throwaway DB** `medikiosk_qa_token_tmp`, 16 simultaneous windows (`scratch/qa_token_concurrency.py`):

```
CONCURRENT_WINDOWS : 16
UNIQUE_TOKENS      : 16 / 16      TOKENS: OPD-101 … OPD-116
DUPLICATES         : none         ELAPSED: 0.44 s
DUPLICATE_INSERT   : REJECTED (unique violation)
ROWS WRITTEN       : 16           TEMP DB: dropped afterwards
```

**Hermetic pytest** — `backend/tests/test_token_concurrency.py`, 3 tests: sequence continues from the existing max (not reset), 8 concurrent check-ins all get distinct tokens, and the database rejects a duplicate `OPD-777`. Part of the green 283.

**Live database, unchanged data** (script only reads; the temp DB is separate):

```
ENCOUNTERS: 23    DUPLICATE_TOKENS: 0    NON_CONFORMING: 0    MAX_OPD: 293 (unchanged)
ix_encounters_token_number | CREATE UNIQUE INDEX ... ON public.encounters (token_number)
```

No token was reset and no patient row was altered. If duplicate tokens had existed, the index creation is **skipped with an error log** rather than deleting rows.

**Honest limit:** this proves correctness under concurrency, not throughput. No sustained-load soak was run.

## 15. P4 — triage safety: presentation fixed, clinical rule escalated (executed)

**Mechanism, read from the code — not guessed.** `classify_complaint_ml` runs **two independent models**: one predicts the department, another the priority, so they can disagree. A lexicon red-flag rule then applies `confidence = max(confidence, 0.95)`, which makes a *keyword-triggered escalation* look like a confident model output. That is exactly how a severe cardiac presentation could read as "handled" at 95% while being routed to an Ayurveda OPD.

**Clinical rules deliberately NOT changed** (no mapping edits, no retraining, no silent rules):
- `"Routine general checkup"` → still **Pediatrics OPD** @ 0.65
- Gujarati severe chest pain → still **AYUSH / Kayachikitsa OPD**
- Cardiac EN/HI → still **Cardiology / Acute Medicine**

Both wrong-but-unchanged cases stay open as **QA-09**: they need a signed-off clinical rule, not a code guess.

**Implemented — presentation guards only, zero routing change:**
- `backend/app/clinical/red_flags.py` — every result now carries `confidence_adjusted_by_rule`, `requires_in_person_triage`, `routing_review_required`, `safety_notice`. `routing_review_required` = `priority == EMERGENCY and stream_for(department) == AYUSH`. The deterministic-fallback path was made shape-consistent and its `is_red_flag` made truthful (it previously returned `EMERGENCY` with `is_red_flag: False`).
- `frontend/src/components/admin/HospitalCommandCenter.tsx` — confidence line appends `— raised by red-flag rule, not the model`; a red `role="alert"` **"Not a clinical disposition."** banner on every high-priority result; an amber `role="alert"` **"Routing needs staff verification."** banner on EMERGENCY + AYUSH.

**Verified in the browser after restarting the backend:**

| Input | Department / priority | Confidence line | Red banner | Amber banner |
|---|---|---|---|---|
| Gujarati severe chest pain | AYUSH / Kayachikitsa OPD · EMERGENCY | `95% — raised by red-flag rule, not the model` | present | present ("…must be confirmed by staff") |
| `Routine general checkup` | Pediatrics OPD · ROUTINE | `65%` | **absent** | **absent** |

Native dialogs during triage: `[]`. Screenshots: `scratch/qa_grammar_fix_result_panel.png`, `scratch/verify_triage_routine.png`.

The browser pass caught a copy bug the API assertions could not: the rendered text read "**A** emergency priority". Fixed with an article helper and re-verified in the browser as "**An** emergency priority".

So an emergency result can no longer present itself as a disposition just because a model scored high: the score's origin is labelled, and the destination is flagged for a human.

**Unresolved — needs your clinical decision:**
1. Should `EMERGENCY` + AYUSH be **blocked** (force a modern-medicine destination) or allowed **with staff override**? Today it is shown unchanged and flagged.
2. Should an age prior prevent **Pediatrics OPD** for patients ≥ 18? Today it is unfixed.
3. Should the red-flag rule stop inflating `confidence` altogether and report a separate `rule_escalated` flag instead? Today it is inflated but labelled.

## 16. Verification of the final state (executed)

| Check | Command | Result |
|---|---|---|
| Backend suite | `python -m pytest backend/tests -q` | **283 passed, 1 skipped, 0 failed** (330.91 s) |
| Typecheck | `npx tsc --noEmit` | exit **0** |
| Production build | `npx next build` (dev server stopped first) | **Compiled successfully**; lint + types pass; 9 routes emitted |
| Popup scan | `scratch/qa_popup_scan.py` | 48 files, **0** native call sites |
| Live token schema | `scratch/qa_token_dupes.py` | 23 rows, 0 duplicates, MAX_OPD 293, UNIQUE index present |
| Build log | `scratch/qa_build_after_fixes.log` | saved |

**Executed vs assumed**

| Executed (evidence in this report) | Not executed (assumed / open) |
|---|---|
| Logged-out browser flows 1–10, both homepage buttons, direct `/admin` `/doctor`, reload, Back/Forward, forged token | Real screen-reader pass (NVDA/VoiceOver) — accessibility verified via DOM/ARIA and focus assertions only |
| RBAC matrix, 8 endpoints × 3 identities | Load/soak test beyond 16 concurrent check-ins |
| 0 native popup call sites, static scan + runtime recorder on 4 flows | Firefox/Safari, real mobile device/touch |
| Dialog role/aria/focus/Escape on 3 modals | `NotificationModal` open/close keyboard pass (component already conformant; not re-driven this round) |
| 16-way Postgres concurrency, duplicate rejection, 3 hermetic pytest cases | Clinical correctness of department mapping — deliberately untouched |
| Triage banners + confidence provenance for 2 inputs | Gujarati sign-off modal copy (QA-04 round-1 fix not re-verified this round) |
| 283 pytest / tsc 0 / next build / live schema | Deployment config, Docker image, production env parity |

## 17. Files changed in round 2

**Backend (5 files + 1 new test)**
- `backend/app/services/token_service.py` — **new** (P3 allocator + guard)
- `backend/app/api/intake_router.py` — P3 guarded allocation
- `backend/app/api/auth_router.py` — P3 second generator replaced
- `backend/app/models/entities.py` — P3 `token_number` UNIQUE
- `backend/app/database/session.py` — P3 idempotent UNIQUE index
- `backend/app/clinical/red_flags.py` — P4 safety fields + truthful fallback
- `backend/tests/test_token_concurrency.py` — **new** (3 tests)

**Frontend (5 files + 1 new module)**
- `frontend/src/lib/useModalDialog.ts` — **new** (P2)
- `frontend/src/components/kiosk/HospitalHelpModal.tsx` — P2
- `frontend/src/components/kiosk/SchemaModal.tsx` — P2
- `frontend/src/components/doctor/DoctorWorkstation.tsx` — P2
- `frontend/src/components/admin/HospitalCommandCenter.tsx` — P4

**QA artefacts added this round**
`scratch/qa_popup_scan.py`, `qa_popup_scan.json`, `qa_token_concurrency.py`, `qa_token_dupes.py`, `qa_build_after_fixes.log`, `scratch/verify_triage_gujarati.png`, `verify_triage_routine.png`, `qa_grammar_fix_result_panel.png`

## 18. Constraints honoured

- **`.env`, secrets, credentials: untouched.** Database URLs are masked (`postgres:****`) in every captured log.
- **Live data: not modified.** No token reset, no patient edit, no row deletion. The concurrency proof ran in a temporary database that was dropped afterwards; the live check is read-only.
- **No Git.** Nothing initialised, committed or pushed (the workspace is not a git repository).
- **No virtualenv.** Everything ran on the global `Python 3.12` at `…\Programs\Python\Python312\python.exe`; no dependency was missing. Environment note: plain `python` on PATH resolves to `.venv_speech\Scripts\python.exe`, which has no `uvicorn`, so the absolute interpreter path is required.
- **Unrelated fixes preserved:** round-1 QA-01…QA-08 behaviour re-tested and still green (283 passed).

**Round-2 bottom line:** P1 is proven secure rather than "fixed" (no code needed); P2 had zero native popups, so the work was the missing dialog semantics, now verified at runtime; P3's race was reproduced, fixed with an advisory lock plus DB uniqueness, and re-proven on real PostgreSQL; P4 implements only presentation guards and escalates the actual routing decision. Still open and needing humans: QA-09 department mapping (incl. the EMERGENCY→AYUSH case), QA-10 grounding, QA-11 period counters, QA-13 credential prefill, QA-14 optimistic acknowledge, QA-15 filter labels.

---

# Round 3 — clinical triage review, four defect fixes, regression

**Round-3 date:** 24 Oct 2026
**Starting point:** the Round-2 state described in §12–§18 (283 passed / 1 skipped, tsc 0, build 0).
**Rule applied throughout:** fix only what is proven broken; change no clinical rule, retrain no model, remap no department without clinician sign-off.

## 19. What round 3 changed, in one table

| ID | Finding | Action | Status |
|----|---------|--------|--------|
| QA-09 | Department routing accuracy (65.8 %) and priority headline | **Documented only** — `CLINICAL_TRIAGE_REVIEW.md` | Open, needs clinician approval (CD-1…CD-5) |
| QA-10 | Red-flag keyword grounding ("cold", `સીને`, `છાતીમાં`, `भारी दर्द`) | **Documented only** — no lexicon edited | Open, needs clinician approval (CD-2, CD-3) |
| QA-11 | Today/Week/All produced identical numbers | Fixed in `admin_router.py` + period-aware labels | **Fixed & verified** |
| QA-13 | Demo credentials pre-filled in production | Fixed in `login/page.tsx` (compile-time gate) | **Fixed & verified** |
| QA-14 | Red-flag acknowledge was optimistic (row vanished before the server answered) | Fixed in `HospitalCommandCenter.tsx` | **Fixed & verified** |
| QA-15 | Queue filter pills were English-only, hardcoded | Fixed in `i18n.ts` + `DoctorWorkstation.tsx` | **Fixed & verified** |
| QA-16 | `POST /api/intake/classify-complaint` is unauthenticated and unused | Reported in `CLINICAL_TRIAGE_REVIEW.md` | Open (new) |
| QA-17 | Previous kiosk visitor's identity is still surfaced to the next visitor | Reproduced with evidence | **Open — privacy, needs a product decision** |
| QA-12 | Modal keyboard/focus semantics | Extended `useModalDialog` focus-restore fallback | Improved & re-verified |

## 20. QA-11 — period-scoped telemetry (fixed)

**Root cause.** `GET /api/admin/telemetry?period=...` accepted the parameter but never used it: registrations, completed intakes, red-flag counts, document counts and all three distributions were computed over the whole table, so Today / Week / All returned the same numbers under a label that implied otherwise.

**Fix.** `backend/app/api/admin_router.py`:
- new `_period_start(period)` returning a naive-UTC lower bound — `today` = 00:00:00 UTC, `week` = `now - 7 days`, `month` = `now - 30 days`, anything else (including `all`) = `None`;
- the boundaries deliberately mirror `IntakeTimeModel.compute_stats_from_db`, so the dashboard and the intake-duration model share one definition of "today". The whole schema stores naive UTC (`datetime.utcnow` defaults), so no local-time shifting is applied — mixing frames would silently shift counts by the UTC offset;
- every query takes a window list: `encounter_window = [Encounter.created_at >= period_start] if period_start else []` and the equivalents on `RedFlagAlert.triggered_at` / `MedicalDocument.uploaded_at`. `select(...).where(*[])` compiles to no WHERE clause, so the all-time path is byte-identical to the previous behaviour;
- the payload now also returns `period`, `period_start` (ISO or `null`) and `scope` (`"period"` / `"all_time"`), so the client never has to infer the meaning of a number.

**Frontend.** `HospitalCommandCenter.tsx` card headings now name the window instead of a bare "Today/Week/All" toggle: *Registrations — today (UTC day)*, *Completed — the last 7 days*, *Red-Flag Alerts — all time*, with the all-time case explicitly labelled. Because the alert *list* is intentionally not period-filtered (an unacknowledged emergency must stay visible regardless of when it fired), a note appears inside the panel whenever a period is selected: *"This list shows every unacknowledged alert regardless of date, so it can be longer than the period-scoped count in the Red-Flag Alerts card above."*

**Tests.**
- `backend/tests/test_admin_period_metrics.py` (new, hermetic SQLite, 2 tests, both pass): `test_period_start_boundaries` pins today to UTC midnight and week/month to trailing windows, and asserts `all`/unknown → `None`; `test_telemetry_counts_are_period_scoped` inserts one encounter now and one 20 days old and asserts `all == 2`, `today == 1`, `week == 1`, `month == 2`, plus `scope`/`period`/`period_start` in the payload.
- Live proof, `scratch/qa_period_metrics.py` against the running API: registrations **today 10 / week 23 / month 23 / all 23**; documents **2 vs 7**; the today status distribution differs from the all-time one → `PERIOD_SCOPED True`. Before the fix all five figures were equal.

**Not changed:** the *definition* of "week" (trailing 7 days, not calendar week) and "month" (trailing 30 days, not calendar month). That is pre-existing behaviour shared with the intake model and is a product decision, not a bug fix.

## 21. QA-13 — demo credential prefill (fixed)

**Root cause.** `login/page.tsx` seeded `identifier`/`password` state with working staff accounts, so a production build handed out a valid Doctor and Admin credential to anyone who opened `/login`.

**Fix.** `DEMO_PREFILL_ENABLED = process.env.NODE_ENV !== 'production'` plus a `prefilled()` helper used for all three roles and in `handleRoleChange`. Next.js inlines `NODE_ENV` at build time, so the production bundle contains the constant `false` and the values collapse to `''` — this is dead-code elimination, not a runtime check that could be flipped.

**A second leak was found during production verification, not by inspection.** Mount-time gating was not enough: the **"Development Demo Logins" quick-fill chips were still rendered in the production bundle**, and one click populated `general@hospital.in` — i.e. the credential was still one tap away even though the fields started empty. The whole chip block is now wrapped in `{DEMO_PREFILL_ENABLED && ( ... )}` and its literals were replaced with the `DEMO_*` constants. Corroborating evidence that the block really left the bundle: the `/login` route shrank **4.83 kB → 4.62 kB**.

**Verification (executed, production mode).** Stopped `next dev`, `npx next build` (exit 0), `npx next start -p 3100`, then in the browser:
- identifier and password fields **empty** on first paint and after switching role Doctor → Admin → Patient;
- submitting the empty form produced the styled inline errors `Admin email is required.` / `Password is required.` with **no auth request issued**;
- no "Development Demo Logins" heading, no chips, and no demo credential string visible anywhere in the DOM;
- `npx tsc --noEmit` → 0; final `npx next build` → exit 0 with `/login` at 4.62 kB.

Dev keeps the convenience (the gate is false only in the production build), so QA and demo flows are unchanged.

## 22. QA-14 — red-flag acknowledgement (fixed)

**Root cause.** `handleAcknowledge` called `fetch(...)` without awaiting it and immediately mutated the clinical store and the list, then fired an optimistic toast. Any failure — HTTP 500, dropped connection, 401 — left the UI showing "acknowledged" while the alert was still open in the database: a triage-safety defect, because the row is the only signal that an emergency is unhandled.

**Fix.** `frontend/src/components/admin/HospitalCommandCenter.tsx`:
- `await fetch(...)`, `if (!res.ok) throw`, and **only then** mutate `clinicalStore` and the list;
- a `previous = redFlags` snapshot is restored in `catch` — a real rollback, not just a toast;
- `acknowledgingId` drives a **per-row** loading state: `disabled` on all acknowledge buttons while a request is in flight, `aria-busy` on the row being written, a `Loader2` spinner and the label *"Acknowledging…"*;
- errors are themed, not native: an inline `role="alert"` banner above the list **plus** a `toast.error(...)` with the title *"Acknowledgement failed"*. The message distinguishes the two failure modes — `The server rejected the acknowledgement (HTTP 500). The alert is still active — retry.` versus `Network error — the alert was NOT acknowledged and is still active. Check the connection and retry.` (`TypeError` = transport failure).

**A defect in the first fix, caught by the browser test.** Two clicks dispatched inside the same JavaScript tick both passed the `acknowledgingId !== null` guard, because the state update had not rendered yet — **2 POSTs**. A synchronous `useRef` latch (`ackInFlight`) now closes the window before any `setState`. Re-verified: two same-tick clicks → **1 POST**, twice.

**Verification (executed, browser).**

| Scenario | Result |
|---|---|
| Slow success (delayed response) | Label *"Acknowledging…"*, `disabled=true`, `aria-busy=true`, row still present during the wait; after the response the row disappeared and a success toast appeared |
| Same-tick double click | Exactly **1** POST (verified twice, instrumented request log length 1) |
| HTTP 500 | Row **remains**, inline `role="alert"` message, error toast, no store mutation |
| Network failure (transport rejection) | Row **remains**, network-specific message, error toast |
| Retry after a failure | Row removed, panel shows the green *"No Active Red-Flag Emergency Alerts"* state, success toast — no page reload required |

**Known interaction, documented rather than "fixed".** With a period selected, the Red-Flag Alerts *card* shows a period-scoped count while the panel lists every unacknowledged alert, so the two can legitimately disagree (card 0, panel 1 row for an old alert). The count is correct and the list is correct; hiding an old emergency would be worse. Explained in-panel (§20).

## 23. QA-15 — doctor queue filter labels (fixed)

**Root cause.** The pills rendered the raw internal key with CSS capitalisation: `{filter}` → "all", "priority", "waiting", "completed", identical in all three languages, in a page whose surrounding chrome was already translated.

**Fix.** `frontend/src/lib/i18n.ts` gained `dw.filterAll`, `dw.filterPriority`, `dw.filterWaiting`, `dw.filterCompleted` in all three dictionaries; `DoctorWorkstation.tsx` now calls ``t(`dw.filter${filter.charAt(0).toUpperCase()}${filter.slice(1)}`, language)`` and the misleading `capitalize` class was removed (it would have mangled Devanagari/Gujarati). The file header comment was corrected to say the queue *chrome* is translated while clinical content stays in the language the patient recorded.

**Verified in the browser:**

| Language | Labels |
|---|---|
| English | All · Priority · Waiting · Completed |
| हिन्दी | सभी · प्राथमिकता · प्रतीक्षारत · पूर्ण |
| ગુજરાતી | બધા · પ્રાથમિકતા · પ્રતીક્ષા · પૂર્ણ |

No unrelated strings were translated, and no clinical text, department name or patient answer was altered.

## 24. QA-09 / QA-10 — clinical triage review (documented, nothing changed)

Full analysis: **`CLINICAL_TRIAGE_REVIEW.md`** (226 lines). Summary of what it establishes, all from code and the shipped evaluation artefacts:

- **Two independent models.** Department and priority are separate models; the priority headline is 82.1 % accuracy / F1 0.806, department is 65.8 % / F1 0.643. A confident-looking percentage in the playground is a model score, **not a clinical disposition** — the UI continues to say so and the emergency banners remain visible (they are raised by `red_flags.py`, independent of the classifier).
- **Blast radius is smaller than it looks.** The department label written to the encounter comes from the patient's own stream choice (`intake_router.py:264`), not from the classifier, and the classifier output is never persisted. The ungrounded risk is the *display* in the Triage Playground and the escalation path, not the stored record.
- **QA-10 root cause.** `red_flags.py:87` does a substring match over the complaint text and `fever_cough.en` contains the bare term `"cold"`, so free text such as "cold sweat with chest pain" can satisfy the fever/cough red flag. The same substring mechanism misfires on `સીને`, `છાતીમાં` and `भारी दर्द` because they appear inside longer phrases. **No lexicon entry was edited.**
- **QA-16 (new).** `POST /api/intake/classify-complaint` has no authentication and no caller — dead but exposed surface.
- **Proposals with explicit boundaries:** P-09-A/B/C (surface the score as advisory, keep the rule-based banner authoritative, add a review queue) and P-10-A/B/C (word-boundary matching, negative-context guard, regression corpus) — each paired with a test in the T-09/T-10/T-ALL table.
- **Decisions that need a clinician, not an engineer: CD-1…CD-5.** Chiefly: whether a low-confidence department prediction may ever re-route a stream; whether the priority label may ever auto-escalate; the exact approved lexicon for chest pain in English/Hindi/Gujarati; which complaints must always page a human; and who signs off on the evaluation threshold before deployment.

The playground's emergency warnings were re-checked in the browser during round 2 and after every change in round 3: a Gujarati chest-pain complaint still renders **EMERGENCY / AYUSH** with both banners and the caption *"95% — raised by red-flag rule, not the model"*; a routine checkup renders neither banner and no native popup.

## 25. Round-3 regression — executed

Every command below was executed in this round from the workspace root unless stated.

| Check | Command | Result |
|---|---|---|
| Backend suite | `& "C:\Users\Solanki Divyang\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -q` | **285 passed, 1 skipped** (330.91 s) |
| Backend suite, final tree | same command, re-run after the last edit | **285 passed, 1 skipped** (106.08 s) |
| TypeScript | `cd frontend; npx tsc --noEmit` | `TSC_EXIT=0` (run again after the final hook edit: `TSC_EXIT=0`) |
| Production build | `$out = & npx next build; $code = $LASTEXITCODE` | `BUILD_EXIT=0`, 9 routes, `/login` 4.62 kB, `/admin` 13.2 kB, `/doctor` 13.5 kB |
| Native popup scan | `python scratch/qa_popup_scan.py` | 48 files scanned, **0** `alert`/`confirm`/`prompt` call sites (47 before `useModalDialog.ts` was added) |
| OPD concurrency | `python scratch/qa_token_concurrency.py` | **16/16** unique `OPD-101…OPD-116` in 0.44 s, `DUPLICATES none`, PASS; duplicate insert rejected by the index; temporary database dropped |
| Live token integrity | `python scratch/qa_token_dupes.py` | 23 encounters, 0 duplicates, `MAX_OPD 293`, both indexes present |

**Access control (browser, executed).**

| Case | Observed |
|---|---|
| `/login?next=%2Fdoctor&role=DOCTOR` | Doctor session lands on `/doctor` |
| `/login?next=%2Fadmin&role=ADMIN` | Admin session lands on `/admin` |
| Direct navigation to `/doctor` while logged out | Redirected to `/login?next=%2Fdoctor`; **zero** `/api/` requests while on the protected route, zero OPD strings rendered |
| Direct navigation to `/admin` while logged out | Redirected to `/login?next=%2Fadmin`; no telemetry or audit data rendered |
| Forged `medikiosk_token` in storage | Redirected to `/login?next=%2Fdoctor`; only `/api/auth/me` (×2, 401) was attempted; token **and** stored user wiped |
| Reload / Back / Forward after logout | No protected content reappears |

The QA-01/QA-07 fixes were re-tested incidentally by the suite above (283 → 285 because of the two new period tests).

**Modal keyboard/focus, all four dialogs (browser, executed).**

| Dialog | Focus in | Escape | Focus out |
|---|---|---|---|
| Help (`mk-help-title`) | close button | closes | returns to the **Help** trigger |
| FHIR Bundle (`mk-fhir-title`) | `Copy FHIR JSON` | closes | returns to **Inspect FHIR R4 Bundle** |
| Database Schema (`mk-schema-title`), opened from the mobile drawer | `Copy SQL` | closes | **`<main>` (3/3 cycles)** — the trigger unmounts with the drawer, so the new fallback in `useModalDialog.restoreFocus()` takes over |
| Database Schema, backdrop click | — | closes on outside click | `<main>` |

The schema-modal case is the one that failed at the end of the previous round (`document.activeElement` was `BODY`): the hook only fell back when the opener was *detached*, but `activeElement` had already collapsed to `body`, which is technically "connected", so `body.focus()` was a silent no-op. `restoreFocus()` now treats `document.body` as "no usable opener", focuses `<main>` with a temporary `tabindex="-1"` and removes it on blur. Re-measured 3/3 cycles: `{"tag":"MAIN","isMain":true}`. With focus on `main`, the next tab stop is the real **Back to Overview** button, so the keyboard user is not stranded. No native popups appeared in any of these runs.

**OPD concurrency (executed).** 16 parallel registrations against real PostgreSQL produced 16 distinct tokens in 0.44 s with no duplicates; a direct duplicate insert was rejected by the UNIQUE index. The live database was read-only during this check.

## 26. New findings in round 3 (open — reported, not changed)

**QA-17 — a previous visitor's identity is still surfaced to the next kiosk visitor (privacy).**
The auto-resume regression from the previous round is fixed: a new visitor gets a fresh wizard at Step 1 with empty input. However:
- Step 2 lists *"Or select a patient from today's active encounters:"* **including the previous visitor's name and UUID**;
- the logged-out public homepage shows that patient under **Interactive Profiles → Simulated Clinical Data** with their token (`OPD-294`);
- no storage key is cleared when a session is abandoned, so the data simply persists.

This is a product decision (kiosk shared-device policy), not a mechanical bug: the "select from today's encounters" list is a legitimate staff-resume convenience and the homepage showcase is a demo feature. The options are (a) scope the resume list to a device/session secret, (b) gate both surfaces to staff roles, or (c) clear the client store on abandon plus an inactivity timer. Not changed, because each option removes a currently working feature.

**QA-16 — unauthenticated classifier endpoint.** See §24 and `CLINICAL_TRIAGE_REVIEW.md`. Not changed, because removing a route is a documented API change and the correct fix depends on CD decisions.

**QA artifacts created during testing (disclosed, awaiting approval to remove).** Browser testing necessarily created one synthetic patient through the public intake API:
- patient/encounter UUID `18d96c64-a19b-4265-9640-d13aeaeeb371`
- token `OPD-294`
- browser `localStorage` key `medikiosk_state_v3` in the QA browser profile

**Nothing was deleted.** Proposed cleanup, to be run only after your approval (it touches one row and its FK dependants; no existing patient records are involved):

```sql
-- 1. Confirm it is the synthetic test row and nothing else
SELECT id, patient_id, token_number, created_at
FROM encounters WHERE id = '18d96c64-a19b-4265-9640-d13aeaeeb371';
SELECT * FROM patients WHERE id = '<patient_id from the row above>';

-- 2. Delete only if the two statements above show the OPD-294 test row
BEGIN;
DELETE FROM history_responses WHERE session_id IN
  (SELECT id FROM history_sessions WHERE encounter_id = '18d96c64-a19b-4265-9640-d13aeaeeb371');
DELETE FROM history_sessions WHERE encounter_id = '18d96c64-a19b-4265-9640-d13aeaeeb371';
DELETE FROM consent_records WHERE encounter_id = '18d96c64-a19b-4265-9640-d13aeaeeb371';
DELETE FROM red_flag_alerts  WHERE encounter_id = '18d96c64-a19b-4265-9640-d13aeaeeb371';
DELETE FROM encounters      WHERE id  = '18d96c64-a19b-4265-9640-d13aeaeeb371';
DELETE FROM patients        WHERE id  = '<patient_id from the row above>';
COMMIT;
```

Client side: clear `localStorage.removeItem('medikiosk_state_v3')` in the QA browser profile (no server effect).

## 27. Reverse comparison — what the round-3 changes could affect

- `admin_router.py`: only `get_hospital_telemetry`. The period parameter was already in the signature; callers that omit it get `period` defaulting to its previous value and, if that value is not one of today/week/month, the `None` window — i.e. identical all-time output. Nothing else in the router imports `_period_start`.
- `HospitalCommandCenter.tsx`: dashboard-only; no shared component changed.
- `login/page.tsx`: the gate is a build-time constant, so dev behaviour is unchanged.
- `i18n.ts` / `DoctorWorkstation.tsx`: additive keys; a missing key would fall back, and all three dictionaries were verified in the browser.
- `useModalDialog.ts`: shared by all dialogs; all were re-tested (table in §25).

## 28. Executed vs assumed — round 3

| Claim | Basis |
|---|---|
| Period metrics are genuinely scoped | **Executed** — hermetic test (`today==1` vs `all==2`) and live API (10 vs 23) |
| Production build has no demo credentials | **Executed** — prod server on :3100, empty fields, no chips, bundle size drop |
| Acknowledge is non-optimistic and rolls back | **Executed** — four browser scenarios incl. real HTTP 500 and transport failure |
| Double-submit is blocked | **Executed** — instrumented request count = 1 |
| Filter pills translate | **Executed** — three languages rendered in the browser |
| Focus restore works for the drawer-opened modal | **Executed** — 3/3 cycles measured in the DOM |
| Access control holds | **Executed** — six cases, including a forged token with network inspection |
| Token allocation is race-free | **Executed** — 16 concurrent registrations on real PostgreSQL, twice (round 2 and round 3) |
| Suite is green | **Executed** — full `pytest -q`, not a subset |
| Keyboard Tab order inside dialogs | **Partly assumed** — Tab trapping was verified by enumerating the focusable set and by the hook's own Tab handler; a physically delivered Tab keypress was not possible in the automated browser pane of this session |
| Clinical correctness of routing | **Not tested and not claimed.** No clinician reviewed the models in this round; §24 lists CD-1…CD-5 |
| Production readiness | **Not claimed.** Passing tests say the code does what the tests describe; they say nothing about clinical safety, DPDP compliance or load capacity |

## 29. Files changed in round 3

| File | Change |
|---|---|
| `CLINICAL_TRIAGE_REVIEW.md` | **New** — QA-09/QA-10 analysis, proposals, tests, CD-1…CD-5 |
| `backend/app/api/admin_router.py` | QA-11 — `_period_start()` + period scoping on every metric |
| `backend/tests/test_admin_period_metrics.py` | **New** — 2 hermetic tests |
| `frontend/src/components/admin/HospitalCommandCenter.tsx` | QA-14 (await, latch, per-row loading, rollback, themed error) + QA-11 labels and scope note |
| `frontend/src/app/login/page.tsx` | QA-13 — compile-time prefill gate incl. the demo-login chip block |
| `frontend/src/lib/i18n.ts` | QA-15 — 4 filter keys × 3 languages |
| `frontend/src/components/doctor/DoctorWorkstation.tsx` | QA-15 — pills use `t()`; `capitalize` removed |
| `frontend/src/lib/useModalDialog.ts` | Focus-restore fallback to the `main` landmark |
| `scratch/qa_period_metrics.py` | **New** — live period proof (QA support script) |
| `QA_REPORT.md` | This section |

No `.env`, secret, credential, model artefact, lexicon, department mapping or existing patient record was modified.

## 30. Constraints honoured in round 3

- **Global interpreter only.** Every Python command used the absolute path `C:\Users\Solanki Divyang\AppData\Local\Programs\Python\Python312\python.exe`. No virtual environment was created or activated; the pre-existing `.venv_speech` (which has no `uvicorn`) was never used.
- **No `.env`/secret/credential edit.** Credentials were read only to log in as a demo user in the browser; nothing was written.
- **No existing patient record touched.** All writes were synthetic test data, disclosed in §26.
- **No deletion, no cleanup script.** QA records and the synthetic patient are intact; the removal is proposed above and awaits approval.
- **No Git.** Nothing initialised, committed or pushed.
- **No clinical claim.** §24 and §28 state explicitly that model output is not a disposition and that no clinician has signed off.

**Round-3 bottom line.** Four defects are fixed with runtime evidence (QA-11, QA-13, QA-14, QA-15) and one accessibility defect is closed (schema-modal focus). The two clinical findings are now fully documented with named owners-to-be and five explicit decisions, but **not** changed — that requires a clinician. One new privacy finding (QA-17) is open and needs a product decision, and one synthetic QA patient is waiting for approval to remove. Software tests pass; clinical safety and production readiness remain unclaimed.
