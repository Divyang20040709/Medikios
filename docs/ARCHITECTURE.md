# MediKiosk — Architecture (Current, Verified Implementation)

> Status: **verified against the code and live checks during Phase 7–8** (209 backend tests,
> frontend build, live-PostgreSQL e2e trace, real OCR smoke test).
> This document supersedes `ARCHITECTURE_AND_IMPLEMENTATION.md` where they conflict;
> the older file remains as a historical reference for UI/UX details.

## 1. Actual Request / Data Flow

```
┌─────────────────────────────── Browser (Next.js 14, port 3000) ───────────────────────────────┐
│  /patient/intake (kiosk)      /doctor (workstation)      /admin (telemetry)   /chat  /login    │
│  i18n: en|hi|gu client dictionary (src/lib/i18n.ts); interview language may differ from UI     │
│  language by design (speechLanguage ?? language).                                            │
│  next.config.js rewrites /api/* → http://127.0.0.1:8000 (override: NEXT_PUBLIC_API_BASE_URL). │
└──────────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                           ▼
┌──────────────────────────── FastAPI backend (uvicorn, port 8000) ─────────────────────────────┐
│ auth_router     JWT issue/verify; bcrypt + legacy SHA-256 auto-upgrade; strict role guards    │
│ intake_router   init (consent PENDING) → /consent (explicit decision) → /answer (red-flag     │
│                 screening per answer) → /followup-questions (local LLM or ontology fallback)  │
│                 → /complete (idempotent; AI draft summary stored separately)                  │
│ document_router upload validation (type/size/empty/encounter-exists) → thread-pool OCR with   │
│                 hard timeout → honest COMPLETED / NO_TEXT / FAILED; PHI reads & downloads     │
│                 behind DOCTOR/ADMIN tokens                                                   │
│ speech_router   /status honesty matrix; /transcribe en|hi|gu; 400/413/503 error contract      │
│ doctor_router   priority queue; dossier (answers + AI draft + OCR entities + flags as         │
│                 separate, labelled blocks); entity verification; summary edit + sign-off      │
│ admin_router    kiosk telemetry, audit views, intake-time prediction                         │
│ fhir_router     local FHIR R4 bundle; ABDM push = recorded simulation                        │
│ chat_router     multilingual chat (LLM-backed if available, scripted otherwise)              │
└──────┬──────────────────────────┬──────────────────────────────┬──────────────────────────────┘
       ▼                          ▼                              ▼
 SQLAlchemy async session  Clinical engines               Service adapters
 (PostgreSQL 127.0.0.1:    ontology.py (question trees,   red_flags.py (deterministic rules —
 5432/medikiosk_db,        10-lang metadata, en/hi/gu     never LLM-dependent; EMERGENCY/URGENT
 asyncpg; visible SQLite   content)                       escalation + RedFlagAlert rows)
 fallback to ./medikiosk.db memory_graph.py (doctor       intake_time_model.py (sklearn)
 when PG unreachable)      relationship graph)            ml/train_models.py (offline retraining)
       │
       ▼
 llm_service (OpenRouter if key configured → else LocalLLMClient Ollama/OpenAI-compat →
   else deterministic text fallbacks; every layer validated by blocklist regexes; AI output
   NEVER overwrites patient answers or a physician-signed summary)
 speech/provider.py (auto: IndicConformer via isolated .venv_speech for hi/gu when
   provisioned, else Whisper CPU, else honest 503) + indicconformer_infer.py
 documents/processor.py (PaddleOCR CPU, enable_mkldnn=False; regex entity extraction with
   per-entity confidence + source snippet; nothing invented — blank scan ⇒ NO_TEXT)
```

Persistence core tables (`backend/app/models/entities.py`): Patient, Encounter, ConsentRecord,
HistorySession, HistoryResponse (verbatim patient answers, `input_method` touch|voice),
RedFlagAlert, ClinicalSummary (draft → signed), MedicalDocument, ExtractedEntity
(`doctor_verified` flag), Medication, Observation, Allergy, Surgery, TimelineEvent,
AuditLog, User, IntegrationEvent. Tables are auto-created at startup; **no migration tool** is used.

## 2. Component Roles

| Component | Role | Implementation status |
|---|---|---|
| React/Next.js | Kiosk UI, doctor workstation, admin portal; client-side i18n (en/hi/gu) | **Verified** — tsc + production build pass |
| FastAPI | Single async API service; routers above; CORS to :3000 | **Verified** |
| PostgreSQL + SQLAlchemy async | Primary datastore (`medikiosk_db`); visible honest SQLite fallback | **Verified** on live local PG (18/18 e2e) |
| Consent flow | Init creates a PENDING ConsentRecord (no `granted_at` stamp); only `POST /api/intake/consent` records an explicit accept/decline; FHIR maps pending/declined as `draft` + `deny` | **Verified** (Phase 7 tests) |
| RedFlagEngine | Deterministic pattern rules per answered section (+ free-text blob scan); creates RedFlagAlert rows, escalates Encounter.priority; independent of any LLM | **Verified** — survives LLM outage/dismissive output |
| Local LLM (Ollama) | Follow-up questions + clinical draft summaries; output passes validation blocklist (no dosages/diagnoses/reassurance); falls back to reviewed ontology questions | **Conditional** — feature-probed at runtime |
| OpenRouter LLM | Used only when an API key is configured; same output guards | **Optional** (key not required) |
| Speech providers | Whisper (CPU, vendored) and optional IndicConformer/NeMo in `.venv_speech`; `/api/speech/status` reports real per-language readiness; failures return honest 4xx/5xx, never fake transcripts | **Environment-dependent** |
| PaddleOCR | CPU-only inference (`enable_mkldnn=False` after the paddlepaddle 3.3.1 oneDNN crash); regex-based clinical entity extraction with source snippets; all entities start unverified | **Verified** via smoke test |
| Authorization | bcrypt hashes (+ transparent SHA-256 upgrade), JWT exp 8 h, `require_authenticated_roles` on every PHI read, clinical action and admin view; kiosk write endpoints intentionally anonymous with uuid4 session IDs | **Verified** (Phases 6–7 tests) |
| FHIR serializers | Local R4 bundle: honest Consent status/provision, provenance tags, opaque document URLs (`api/documents/file/{id}`), Composition preliminary→final on sign-off | **Verified locally; NOT externally validated** |
| ABDM push | Validates nothing external; writes `IntegrationEvent` and returns `SIMULATED_NOT_TRANSMITTED` | **Simulated — clearly labeled** |

## 3. Data Provenance Rules (enforced in code)

1. Patient answers (`HistoryResponse`) are written only by `/api/intake/answer` and are never mutated by AI or doctor edits — the doctor dossier shows them verbatim as "Patient's Own Words".
2. AI draft (`ClinicalSummary`) is created once at `/complete` (idempotent); physician edits are revision-counted and audited; after sign-off, regeneration endpoints return 409.
3. OCR entities keep `doctor_verified=False` until `POST /api/doctor/verify-entity/{id}` (DOCTOR-only, audited).
4. Every state change (consent decision, intake init/complete, OCR outcome, verification, sign-off, PHI download, hash upgrade) writes an `AuditLog` row.
5. FHIR/queue/dossier export only what actually happened: pending consent → `draft`/`deny`, unsigned summary → `preliminary`, failed OCR → `FAILED`, never optimistic defaults.

## 4. Deliberate Design Decisions (do not "fix" these)

- **Semantic retrieval rejected (Phase 5):** follow-up routing uses keyword→ontology trees; the multilingual embedding evaluation did not meet the adoption gate. `QDRANT_*` vars are unused.
- **Anonymous kiosk writes:** shared-device intake has no patient login; boundary = unguessable uuid4 session/encounter IDs (documented risk in security doc).
- **Whisper fixed to CPU:** GPU (sm_120) caused CUDA failures on the dev machine; NeMo path is isolated in `.venv_speech`.
- **PaddleOCR MKLDNN disabled:** paddlepaddle 3.3.1 oneDNN crashes on PIR attributes (`ConvertPirAttribute2RuntimeAttribute`); CPU-only is the verified compatible configuration.
