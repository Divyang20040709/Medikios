# MediKiosk — AI-Assisted Clinical Intake Platform

> **Smart India Hackathon • Academic Prototype**
> AI-powered patient case-taking & OPD optimization platform for high-volume hospital outpatient departments.

> **⚠️ Academic Prototype Disclaimer** — MediKiosk is an academic demonstration prototype.
> It is **not** a certified medical device, **not** a diagnostic system, and **not** a
> production-ready hospital deployment. It performs **no autonomous diagnosis**:
> consulting physicians remain the final clinical authority for every record.
> ABDM/FHIR integration is locally generated and **simulated** — nothing is transmitted
> to any live health gateway, and no ABDM certification exists.

---

## 1. Overview, Purpose & Scope

Indian hospital OPDs leave only 2–4 minutes per consultation. MediKiosk shifts structured
history-taking and paper-record digitization to a patient-facing kiosk while keeping the
physician in full control:

- **Structured multilingual intake** (English, Hindi, Gujarati) by touch or voice.
- **Deterministic red-flag triage** that instantly escalates emergency patterns in the doctor queue — never dependent on any AI service.
- **AI-assisted draft summaries and follow-up questions** from a *local* LLM (Ollama) when provisioned, with honest rule-based fallback when not.
- **Prescription/lab OCR** with per-entity confidence; extracted entities stay **unverified** until a doctor confirms them.
- **Physician sign-off workflow**: edits, verification, and a signed final summary that AI can never overwrite.
- **DPDP-style consent gate**: consent remains **pending** until the patient explicitly accepts on the consent screen.
- **FHIR R4 export** (local, schema-consistent) and a clearly-labeled **simulated** ABDM push.
- **Full audit trail** of consent, intake, OCR, verification, and sign-off events.

### Complete patient → doctor workflow

```
Language select → Check-in (encounter + token, consent PENDING)
→ Explicit consent decision (POST /api/intake/consent)
→ SOCRATES interview (text/voice) → deterministic red-flag screening per answer
→ Optional local-LLM follow-up questions (safe ontology fallback)
→ Document upload + OCR (honest NO_TEXT / FAILED on problems)
→ Intake completion → AI draft summary (draft only)
→ Doctor queue (EMERGENCY first) → dossier: patient's own words + AI draft + OCR + alerts
→ Doctor verifies OCR entities → edits & signs summary (FINALIZED, immutable to AI)
→ Audit log + FHIR bundle reflect the true final state
```

## 2. Technology Stack & Architecture

| Layer | Technology | Status |
|---|---|---|
| Frontend | Next.js 14 (App Router), React 18, Tailwind CSS, TypeScript | Verified (tsc + build pass) |
| Backend | FastAPI, Python 3.10+ (developed on 3.12), SQLAlchemy 2.0 async, Pydantic v2 | Verified |
| Database | Local PostgreSQL (asyncpg) **primary**; automatic visible SQLite fallback | Verified against live local PG |
| Speech | Local Whisper (CPU) + optional NVIDIA IndicConformer (NeMo, isolated `.venv_speech`) | Environment-dependent; honest `/api/speech/status` |
| OCR | Local PaddleOCR (vendored `model/paddleocr`, CPU, `enable_mkldnn=False`) | Verified (smoke test extracts real text) |
| LLM | Optional local Ollama (`llama3.2`) or OpenRouter key; deterministic fallback otherwise | Conditional by design |
| ML models | Scikit-Learn triage classifier + intake-duration regressor (trained on Synthea / Med-Dialog) | Verified artifacts under `model/` |
| Interop | HL7 FHIR R4 serializers (Patient, Encounter, Consent, Observation, MedicationRequest, DocumentReference, Composition) | Local generation only — NOT externally validated |
| ABDM | Sandbox simulation — no gateway connectivity | Explicitly simulated |

Full request/data flow, module responsibilities and honesty contracts: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
The older `ARCHITECTURE_AND_IMPLEMENTATION.md` is a historical reference; where they conflict, `docs/` wins.

## 3. Repository Structure

```
backend/          FastAPI app (api routers, clinical engines, services, models, tests, uploads/)
frontend/         Next.js app (kiosk /patient/intake, /doctor, /admin, /chat, /login)
model/            Trained ML artifacts + vendored paddleocr & whisper packages
datasets/         Public training corpora (Synthea, Med-Dialog, IndicVoices) — not patient data
scripts/          Speech-env setup + historical patch scripts
docs/             Architecture, Windows setup, security & safety, demo guide, release checklist
scratch/          Disposable verification scripts (git-ignored)
.env.example      Configuration template (copy to .env)
```

## 4. Prerequisites & Local Setup

- Python 3.10+ (3.12 used for all verification) and Node.js 18+
- Optional: local PostgreSQL 16 (the app honestly falls back to SQLite and reports it at `/health`)
- Optional: Ollama for AI follow-ups/summaries; NeMo environment for IndicConformer speech
- **Windows-specific verified setup (venv, dependencies, PostgreSQL, startup, troubleshooting):** see **[docs/WINDOWS_SETUP.md](docs/WINDOWS_SETUP.md)**

Quick start:

```powershell
# 0. Configure environment (first time)
Copy-Item .env.example .env       # then edit JWT_SECRET and DB settings

# 1. Backend (from the repository root)
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 2. Frontend (separate terminal)
cd frontend; npm install; npm run dev     # http://localhost:3000
```

API docs: `http://localhost:8000/docs` • Health: `http://localhost:8000/health` (reports the **actual** DB connection, not just config).

### Database behavior (verified quirk — read before configuring)

- The app resolves PostgreSQL from `NEON_DATABASE_URL`, `DATABASE_URL`, `POSTGRES_URL` or `POSTGRESQL_URL` (first non-empty, non-sqlite), or discrete `POSTGRES_*` vars.
- **Credentials** come from `POSTGRES_USER/PASSWORD` or the URL alias, but the **host/port/database always come from `POSTGRES_HOST` (127.0.0.1), `POSTGRES_PORT` (5432), `POSTGRES_DB` (`medikiosk_db` by default)** — the database name embedded in a URL alias is intentionally ignored (`backend/app/core/config.py`).
- If PostgreSQL is unreachable, the server **visibly** falls back to `sqlite+aiosqlite:///./medikiosk.db`, logs the real error, and `/health` reports `fallback_in_use: true`. It never silently claims PostgreSQL readiness.
- Tables are created automatically at startup (`Base.metadata.create_all`) — there are **no Alembic migrations** in this project.

## 5. Environment Variable Reference

All variables live in `.env` (never commit it — `.gitignore` covers `.env`, `*.db`, `backend/uploads/*`). See `.env.example` for the full template. **No secret values are documented here.**

| Variable | Purpose | Default / Note |
|---|---|---|
| `DATABASE_URL` / `NEON_DATABASE_URL` / `POSTGRES_URL` | PostgreSQL alias (parsed for credentials) | Optional; see §4 |
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | Discrete DB settings; host/port/DB decide the real target | `127.0.0.1 / 5432 / medikiosk_db` |
| `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Token signing/expiry (8 h default) | Server warns loudly if the built-in dev secret is kept |
| `OPENROUTER_API_KEY/MODEL/BASE_URL` | Optional hosted LLM | Empty ⇒ local/deterministic paths only |
| `LOCAL_LLM_ENABLED`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `LLM_TIMEOUT_SECONDS` | Local Ollama integration | Optional; falls back safely |
| `SPEECH_PROVIDER` (`auto`/`whisper`/`indicconformer`), `WHISPER_MODEL_PATH/SIZE/DEVICE` | Speech stack | Whisper pinned to CPU |
| `BHASHINI_API_KEY/USER_ID/PIPELINE_ID` | Optional cloud ASR (unconfigured) | Blank = disabled |
| `OCR_PROVIDER`, `PADDLEOCR_MODEL_PATH`, `MAX_DOCUMENT_UPLOAD_MB`, `OCR_TIMEOUT_SECONDS` | Local OCR | `paddleocr / 25 MB / 90 s` |
| `QDRANT_URL/API_KEY` | **Not used** — semantic retrieval was evaluated and rejected | Leave blank |
| `ABDM_CLIENT_ID/SECRET/BRIDGE_URL/MODE` | ABDM section is **simulated** regardless of values | `sandbox` |
| `BACKEND_PORT`, `BACKEND_CORS_ORIGINS`, `NEXT_PUBLIC_API_BASE_URL` | Ports/proxy | 8000 / 3000; Next rewrites `/api/*` |

## 6. Test, Type-Check & Build Commands

```powershell
python -m pytest                                  # full backend suite (209 passed, 1 skipped at final verification)
python -m pytest backend/tests/test_integration_phase7.py -q   # end-to-end integration tests
cd frontend; npx tsc --noEmit                     # exit 0
cd frontend; npm run build                        # production build, exit 0
python scratch\p7_pg_e2e.py                       # optional: live-PostgreSQL e2e trace (self-cleaning)
```

## 7. Demo Workflow

Step-by-step demonstration script with expected results and fallbacks: **[docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)**.
Seed the demo dataset first: `python -m backend.app.scripts.seed` (bcrypt-hashed synthetic staff accounts; details in the demo guide).

## 8. Machine Learning Artifacts

Trained offline on public datasets — metrics reproduced by `python -m backend.app.ml.train_models`:

| Model | Dataset | Artifact | Verified metrics |
|---|---|---|---|
| Clinical triage classifier | Med-Dialog + Synthea | `model/clinical_triage_classifier.joblib` | Priority acc 82.1 %, F1 0.806, Dept acc 65.8 % |
| Intake duration regressor | Synthea ambulatory | `model/intake_duration_regressor.joblib` | MAE 0.25 min, R² 0.958 (5-fold CV 0.953) |
| Indic clinical lexicon | IndicVoices (hi/gu) | `model/indic_clinical_lexicon.json` | Match acc 83.3 % |

## 9. Current Limitations & Future Improvements

**Limitations (honest, current state):** documented fully in [docs/SECURITY_AND_CLINICAL_SAFETY.md](docs/SECURITY_AND_CLINICAL_SAFETY.md) — including anonymous kiosk write surfaces protected only by unguessable UUIDs, patient login without passwords, no rate limiting or token revocation, no doctor↔patient assignment model, interview localized to en/hi/gu (10 languages listed server-side but question/voice coverage is en/hi/gu), OCR tuned for English print scans, FHIR unvalidated externally, ABDM simulated.

**Future work (not implemented):** ABDM certification + live gateway onboarding, patient identity verification at kiosk, structured Indic OCR models, embeddings/RAG (explicitly rejected in Phase 5 pending corpus growth), hospital pilot hardening (rate limits, session management, HL7 validation).

## 10. Docker (optional)

`docker-compose.yml` builds backend + frontend (SQLite inside containers, uploads volume mounted). It has **not** been re-verified in this Phase 8 check run — treat as convenience, not the primary path.
#   M e d i k i o s  
 