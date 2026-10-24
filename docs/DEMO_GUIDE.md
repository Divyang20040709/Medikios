# MediKiosk — Academic Demonstration Guide

> 8-step showcase script with expected results and honest fallbacks.
> **Synthetic data only** — every name, history and document below is fictional.
> Prerequisite: app running per `docs/WINDOWS_SETUP.md` (backend :8000, frontend :3000).
> Before going on stage, check `GET /api/health/diagnostics` and `GET /api/speech/status`
> to know which optional services are actually live on the demo machine.

## 0. Start the application and database

```powershell
# Terminal 1 (repo root) — PostgreSQL must be running for the PG showcase
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# Terminal 2
cd frontend; npm run dev
```

Seed if not done yet: `python -m backend.app.scripts.seed`
(synthetic staff `doctor@hospital.in / doctor123`, `admin@hospital.in / admin123`;
synthetic patients Ramesh Kumar / Sunita Devi / Arjun Singh with histories).

**Expected:** startup banner shows the real DB backend (`postgresql` — or a very visible
ERROR banner + SQLite fallback, which is itself worth pointing out as honest behavior).
`http://localhost:3000` loads the kiosk.

## 1. Patient intake + explicit consent (the headline privacy moment)

On `/patient/intake`: register a new synthetic patient (e.g. *Priya Patel, 34, F, English*),
pick "Chest pain" as the complaint.

**Show:** the consent screen appears and **nothing is recorded until the patient decides**.
Accept consent on the kiosk.
**API proof (optional, impressive):** before the click,
`GET /api/doctor/queue` (as doctor) or the DB shows the `ConsentRecord` as *pending*;
after the accept it is explicitly granted with a timestamp and a `CONSENT_GRANTED` audit row.

**Expected:** questions only start after explicit acceptance. Declining (try it on a second
session) leaves consent declined, is audited, and no interview data is collected.

## 2. Symptoms + red-flag case (deterministic escalation)

Continue the same session and answer the chest-pain interview:
- Site: **"Pain at center of chest"**
- Radiation: **"Spreads to left arm"**

**Show:** the red-flag banner appears *immediately on that answer* and the encounter jumps to
**EMERGENCY** in the doctor queue — before any AI has spoken.
**API proof:** even with Ollama stopped, the same two answers escalate (red flags are pattern
rules in `red_flags.py`, never LLM-dependent — say this out loud).

**Expected:** queue shows the new patient at top with `EMERGENCY`; `GET /api/admin/red-flags`
(admin token) lists the alert. Follow-up questions still work with LLM offline — they degrade
to the reviewed ontology question set.

## 3. Speech and OCR — only if provisioned (be honest either way)

**Speech:** ask the audience to check `GET /api/speech/status` first.
- If a language shows `available`, record a few words of Hindi/Gujarati/English on the kiosk
  and show the transcript feeding the answer box.
- If **not** available → the endpoint returns a clean **503** and the kiosk falls back to typed
  input. Demonstrate the fallback and state: *"the system refuses to fake a transcript."*
  (IndicConformer requires the separate `.venv_speech` + 2.4 GB model; Whisper runs CPU-only.)

**OCR:** upload a synthetic prescription — type something like
`PRESCRIPTION / Tab Paracetamol 500 mg / HbA1c 8.1 %` in any editor, screenshot it, upload
as `.jpg/.png` from the intake document step.
**Expected:** extraction returns visible text + entities (medication, observation), each
**unverified** with `confidence` and a source snippet. Upload a blank image instead and point
out the honest `NO_TEXT` state — the pipeline invents nothing.
If PaddleOCR isn't installed on the demo machine, the upload records a failed/empty state and
the flow continues — mention it as environment-dependent.

## 4. Doctor workstation — four provenance lanes

Log in at `/doctor` as `doctor@hospital.in / doctor123`. Open the EMERGENCY patient's dossier.

**Point out the four separate, labelled blocks:**
1. **Patient's Own Words** — verbatim answers (`input_method` shows touch vs voice),
2. **AI-generated draft summary** — clearly marked as a draft,
3. **OCR-extracted entities** — marked *unverified*,
4. **Red-flag alerts** — deterministic, with the triggering phrase.

**Expected:** nothing mixes lanes — this is the architectural claim of the project.

## 5. Verify an OCR entity and sign off

1. Click **verify** on the extracted Paracetamol entity → it flips to doctor-verified (audited).
2. Optionally edit the summary (revision count increments, old state kept in audit), then
   **Confirm & Sign** → encounter becomes **FINALIZED**.
3. **Try to break it (great demo moment):** with the doctor token, call
   `POST /api/doctor/encounter/{id}/generate-llm-summary` again → **409** —
   *"AI cannot overwrite a signed physician record."* Re-signing also returns 409.
4. Show that the **admin** account (`admin@hospital.in / admin123`) **cannot**
   sign off — 403. Administrative and clinical authority are separate.

## 6. Final status, audit trail, FHIR output

- Queue: the signed encounter no longer appears in the active queue (finalized + idempotent
  completion: calling `/api/intake/complete/{session_id}` twice returns `already_completed`).
- `GET /api/admin/audit-logs` (admin token): the real action chain — `INTAKE_INITIALIZED` →
  `CONSENT_GRANTED` → `DOCUMENT_OCR_PROCESSED` → `INTAKE_COMPLETED` → `OCR_ENTITY_VERIFIED` →
  `DOCTOR_CONFIRMED` → `DOCUMENT_DOWNLOADED` (PHI access). Red flags are shown as
  `RedFlagAlert` rows via `GET /api/admin/red-flags` (they are alert records, not audit actions).
- **FHIR:** `GET /api/fhir/encounter/{id}` (doctor token) — show the R4 bundle: consent
  (honest `active`/`draft`/`revoked` mapping), observations with provenance tags, signed
  Composition as `final`, patient statements as `text` with source = patient.
  **Say explicitly:** locally generated, not externally validated, not ABDM-certified.

## 7. Security theater — unauthorized access & simulated ABDM

In PowerShell (no token / wrong role):

```powershell
Invoke-RestMethod http://localhost:8000/api/doctor/queue            # -> 401 (no token)
# admin token used for sign-off                                    # -> 403 (tested)
# staff login without password                                    # -> 401 "Password is required"
```

**ABDM push:** `POST /api/fhir/abdm/push/{encounter_id}` (doctor token) returns
`SIMULATED_NOT_TRANSMITTED` and writes only a local `IntegrationEvent` row.
**State clearly:** no data left the machine; ABDM integration is architectural demonstration,
not live or certified.

## 8. Close with the honest limitations slide

- Academic prototype — not a medical device, not diagnostic, not production-ready.
- No login rate limiting, no token revocation, no doctor↔patient assignment (documented in
  `docs/SECURITY_AND_CLINICAL_SAFETY.md`).
- Speech/LLM/OCR are environment-dependent; the app reports their real state.
- All data shown is synthetic; FHIR/ABDM are local/simulated respectively.

## Fallback cheat-sheet

| If unavailable | Do instead |
|---|---|
| PostgreSQL down | Let the visible SQLite fallback run and show `/health` reporting `fallback_in_use: true` — honesty is part of the story. |
| Ollama / LLM | Skip AI follow-ups demo; show ontology fallback questions still work and state AI is conditional. |
| Speech providers (503) | Show typed fallback + `/api/speech/status` matrix. |
| PaddleOCR missing | Show upload failing honestly; walk through a pre-extracted dossier from seeded data. |
| Frontend build issue | `npm run dev` was verified in Phase 8; as last resort demo via the API with the curl-equivalent PowerShell calls above. |
