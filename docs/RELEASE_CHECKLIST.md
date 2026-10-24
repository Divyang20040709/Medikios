# MediKiosk — Release Checklist (Phase 8, executed 2026-10-23)

> Every result below is from a command actually run on the reference machine
> (Windows, PowerShell 5.1, Python 3.12.10, Node v24.20.0, local PostgreSQL on 5432).
> Nothing here claims a clean-room install, external validation, or certification.

## 1. Automated checks — fresh run (after all doc/cleanup edits)

| Check | Command | Result |
|---|---|---|
| Backend test suite | `python -m pytest` | ✅ **209 passed, 1 skipped** in 50.92 s (skip = optional speech-env test) |
| Phase 7 integration tests | `python -m pytest backend/tests/test_integration_phase7.py` | ✅ 38 passed (subset of the 209) |
| Frontend type-check | `npx tsc --noEmit` (in `frontend/`) | ✅ exit 0, no errors |
| Frontend production build | `npm run build` (in `frontend/`) | ✅ exit 0 |
| Live PostgreSQL E2E trace | `python scratch\p7_pg_e2e.py` | ✅ **18/18** against `medikiosk_db` (creates + deletes its own synthetic rows) |
| OCR smoke test (real engine) | `python scratch\p8_ocr_smoke.py` (run pre-deletion) | ✅ `SMOKE_RESULT: TEXT_EXTRACTED` — "PRESCRIPTION / Tab Paracetamol 500 mg / HbA1c 8.1 %" |
| App health truthfulness | `GET /health`, `GET /api/health/diagnostics` | ✅ report the real DB backend and masked config previews |

Not performed (do not claim them): clean-room install in an isolated environment, load/pen testing,
FHIR external conformance validation, Docker deployment (`docker-compose.yml` references a stale
`NEON_DATABASE_URL` scheme and was **not verified** this phase), ABDM live transmission (code is
an explicit simulation).

## 2. Environment / configuration sanity

| Item | Status |
|---|---|
| `.env.example` | ✅ complete and truthful; env var reference in README §5 matches `core/config.py` |
| `.gitignore` | ✅ covers `.env`, `*.db`, `backend/uploads/`, `scratch/`, `.venv*`, `node_modules`, `.next`, the 2.4 GB `.nemo` model |
| Live `.env` in handover folder | ⚠️ contains a **real local PostgreSQL password and a non-default JWT_SECRET** — values not printed here. **Must be removed/rotated before sharing the project.** |
| `backend/requirements.txt` | ✅ matches the working runtime; OCR extras (paddlepaddle==3.3.1, paddleocr==3.7.0) intentionally documented separately in `docs/WINDOWS_SETUP.md` |
| JWT dev-default secret | ✅ server prints an explicit startup warning if unchanged |
| Secrets scan of tracked source | ✅ no API keys/tokens/passwords in app code; only false positives from the public MedDialog dataset text ("patient: …" lines) |
| Real patient data scan | ✅ none — all DB/upload content is synthetic (seed script + generated images) |
| Debug logging audit | ✅ no request-body/PHI logging; startup banners print connection errors and masked previews only |

## 3. Repository artifacts

**Removed in Phase 8 (verified disposable):**
- `test_here.py` (2-line print script)
- `scratch/p8_ocr_smoke.py` (throwaway OCR check)

**Kept intentionally:**
- `scratch/p7_pg_e2e.py` — rerunnable live-DB verification, referenced by setup docs
- `scratch/update_doctor_workstation.py`, `scripts/patch_*.py`, `apply_updates.py` — historical
  one-off migration/patch scripts from earlier phases; harmless, left untouched (deleting
  project files without explicit instruction is out of scope)
- `backend/medikiosk.db`, root `medikiosk.db` — local SQLite fallback data (gitignored)
- `backend/uploads/*.jpg` — synthetic blank test uploads (gitignored)

**⚠️ Remaining temporary artifacts that could NOT be deleted (tool failure 4× total —
"recordFileDelete returned false", suspected OneDrive/IDE lock on binary files):**
- `scratch/p7_ocr_smoke.png` (13,584 B)
- `scratch/p8_ocr_smoke.png` (13,584 B)
Both are generated synthetic prescription images (no PHI, gitignored directory). **Manual delete
is safe and recommended.**

## 4. Capability status matrix (documentation claims = code reality)

| Capability | Status |
|---|---|
| Consent (pending → explicit decision, audited, idempotent) | ✅ Verified |
| Deterministic red flags (LLM-independent, EMERGENCY escalation) | ✅ Verified |
| Doctor queue / dossier provenance lanes / verify-entity / sign-off (409 immutability) | ✅ Verified |
| RBAC on PHI; admin-cannot-sign; staff password mandate; bcrypt + SHA-256 upgrade | ✅ Verified |
| Audit trail (real action names documented in DEMO_GUIDE §6) | ✅ Verified |
| Idempotent intake completion | ✅ Verified |
| PostgreSQL primary + visible honest SQLite fallback | ✅ Verified live (18/18) |
| FHIR R4 bundle export | ✅ Verified locally — ⚠️ NOT externally validated / not ABDM-certified |
| Text i18n en/hi/gu (client + ontology) | ✅ Verified; ontology metadata lists 10 languages (server-side metadata only — UI ships 3) |
| Local LLM follow-ups/summaries (Ollama/OpenRouter + fallbacks) | ⚠️ Conditional on runtime availability |
| PaddleOCR extraction | ✅ Verified this machine; environment-dependent (not in requirements.txt) |
| Whisper STT (CPU) / IndicConformer STT | ⚠️ Environment-dependent; honest 400/413/503 contract verified |
| ABDM push | 🧪 Simulated — returns `SIMULATED_NOT_TRANSMITTED` by design |
| Rate limiting / token revocation / doctor↔patient assignment | ❌ Not implemented (documented as gaps) |
| Docker / cloud deployment | ❌ Unverified — do not demo as "ready" |

## 5. Documentation set (Phase 8 deliverables)

- `README.md` — rewritten; stale LangGraph/Qdrant/Neon/10-language/"30 tests"/`backend\.venv`
  claims removed; all commands/paths re-checked against the repo.
- `docs/ARCHITECTURE.md` — actual verified flow; supersedes
  `ARCHITECTURE_AND_IMPLEMENTATION.md` (which now carries a supersession banner).
- `docs/WINDOWS_SETUP.md` — executed PowerShell commands, DB quirks, troubleshooting.
- `docs/SECURITY_AND_CLINICAL_SAFETY.md` — implemented protections + explicit gap list.
- `docs/DEMO_GUIDE.md` — 8-step synthetic-data showcase with expected results and fallbacks.
- `docs/RELEASE_CHECKLIST.md` — this file.

## 6. Go/no-go

**GO for academic demonstration** on a machine matching `docs/WINDOWS_SETUP.md`.
Before handover/sharing, two manual steps remain: (1) strip credentials from `.env`
(replace live values / rotate the DB password and JWT secret), (2) delete the two
`scratch/p*_ocr_smoke.png` leftovers.
