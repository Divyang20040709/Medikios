# MediKiosk — Windows Setup Guide (PowerShell)

> Verified on: Windows 11 24H2-class build, PowerShell 5.1, Python 3.12.10, Node v24.20.0,
> local PostgreSQL 16 on `127.0.0.1:5432`. Commands below were executed during Phases 6–8
> unless explicitly marked *recommended but not clean-room tested*.
> PowerShell 5.1 does **not** accept `&&` — separate commands with `;`.

## 0. Prerequisites

| Tool | Required | Verified version |
|---|---|---|
| Python 3.10+ | yes | 3.12.10 |
| Node.js 18+ / npm | yes | v24.20.0 |
| PostgreSQL (local) | optional — SQLite fallback works and says so | local PG on 5432 |
| Ollama | optional — AI follow-ups/summaries degrade to ontology questions | — |
| GPU/torch/NeMo | optional — IndicConformer only; Whisper runs CPU-only | — |

Work from the repository root (path contains spaces — keep the quotes):

```powershell
cd "C:\Users\<you>\OneDrive\Desktop\Medikiosk-main"
```

## 1. Python environment

The reference machine runs the backend on **global Python 3.12** (no `backend\.venv` exists —
older README instructions mentioning one were wrong and have been corrected). A dedicated
venv is *recommended for handover but a fresh clean-room install was not performed in
Phase 8*:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

OCR extras are **not** in `requirements.txt` (they are heavy CPU wheels). The verified
working set is:

```powershell
python -m pip install paddlepaddle==3.3.1 paddleocr==3.7.0
```

PaddleOCR **must run with MKLDNN disabled** — the app already does this
(`enable_mkldnn=False` in `backend/app/documents/processor.py`) because paddlepaddle 3.3.1's
oneDNN path crashes on paddlex 3.7.x PIR attributes. Do not re-enable it, do not switch to GPU.

Optional speech environment (creates `.venv_speech`, downloads torch; the 2.4 GB
`indicconformer_stt_multi_hybrid_rnnt_600m.nemo` model is expected at the repo root):

```powershell
.\scripts\setup_speech_env.ps1
```

## 2. Configure `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Minimum edits:

1. `JWT_SECRET` — set a unique random string (the server prints a warning if the dev default stays).
2. Database — **prefer the discrete variables** over a URL:

```ini
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=medikiosk_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<your local password>
```

### Actual connection behavior (verified — important quirks)

- The connection **target is always `POSTGRES_HOST:POSTGRES_PORT/POSTGRES_DB`** (defaults
  `127.0.0.1:5432/medikiosk_db`). A database name embedded in a `DATABASE_URL`/`NEON_DATABASE_URL`
  alias is **ignored** on purpose — only its user/password are used when the discrete vars are empty
  (`backend/app/core/config.py`, `database_url` property).
- **If your password contains `@` or other URL-special characters, use `POSTGRES_USER`/`POSTGRES_PASSWORD`
  instead of putting it in a URL** — URL parsing of multi-`@` strings is the classic failure here.
- If PostgreSQL is unreachable the app **visibly** falls back to `sqlite+aiosqlite:///./medikiosk.db`,
  logs the real error at startup, and `/health` reports `"fallback_in_use": true`. It never
  silently pretends PostgreSQL is up.
- Tables are created automatically on startup. **There are no migrations to run** (no Alembic in this project).

## 3. PostgreSQL (first time)

Using psql as a superuser (`psql` ships with the Windows PostgreSQL install):

```powershell
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE medikiosk_db;"
```

(Only the database is needed — roles/columns are created by the app; `init_db` also aligns
a few legacy `users` columns automatically.)

## 4. Seed the demo data (optional but recommended)

```powershell
python -m backend.app.scripts.seed
```

Creates synthetic staff (bcrypt-hashed: `doctor@hospital.in / doctor123`,
`admin@hospital.in / admin123`) and three synthetic patients with clinical history —
all fictional, see `docs/DEMO_GUIDE.md`.

## 5. Start the application

Terminal 1 — backend (from the repository root):

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend:

```powershell
cd frontend
npm install
npm run dev          # http://localhost:3000
```

The Next.js dev server rewrites `/api/*` to `http://127.0.0.1:8000` (`frontend/next.config.js`);
`NEXT_PUBLIC_API_BASE_URL` overrides the proxy target if the backend moves.

Sanity check (values shown, no secrets ever printed):

```powershell
Invoke-RestMethod http://localhost:8000/health | ConvertTo-Json -Depth 5
Invoke-RestMethod http://localhost:8000/api/health/diagnostics | ConvertTo-Json -Depth 5
```

Expect `database.connected: true` with `active_backend: postgresql` (or an honest
`fallback_in_use: true` when PG is down).

## 6. Tests, type-check, production build

From the repository root (`pytest.ini` sets `pythonpath=.`):

```powershell
python -m pytest                                            # full suite: 209 passed, 1 skipped (final Phase 8 run)
python -m pytest backend/tests/test_integration_phase7.py   # e2e integration tests
cd frontend; npx tsc --noEmit; npm run build                # both exit 0
```

Live-database end-to-end trace (creates and deletes its own synthetic rows):

```powershell
python scratch\p7_pg_e2e.py        # 18/18 against local medikiosk_db
```

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Startup banner `*** ERROR: Could NOT connect to PostgreSQL ***`, app runs anyway | PG service down / wrong credentials → the visible SQLite fallback is active. Start PG (`Get-Service postgresql* \| Start-Service`) or fix `.env`; check `/health`. |
| `InvalidCatalogNameError database "X" does not exist` after setting `DATABASE_URL` | Expected: the URL's DB name is ignored; create/point `POSTGRES_DB` at the real DB (`medikiosk_db`). |
| Login as DOCTOR/ADMIN returns 401 `Password is required for staff sign-in` | By design since Phase 6 — staff must send a password; seed accounts above. |
| `OSError: [WinError 127]` or bcrypt backend errors | `requirements.txt` pins `bcrypt<4.1` for passlib compatibility — reinstall pinned version. |
| OCR: `NotImplementedError ... ConvertPirAttribute2RuntimeAttribute ... onednn_instruction.cc` | Someone re-enabled MKLDNN or changed paddle versions. Restore `enable_mkldnn=False` (processor.py) and the pinned paddle 3.3.1/3.7.0 set. |
| Voice: `/api/speech/transcribe` → 503 | Provider genuinely not provisioned (no NeMo env / model files). Kiosk falls back to text input — check `GET /api/speech/status` for the real per-language readiness. Do not fake transcripts. |
| `python -m uvicorn backend.app.main:app` fails with `ModuleNotFoundError: backend` | Run from the repository root (not from `backend/`); `pytest.ini`/`main.py` both assume root invocation. |
| PowerShell rejects `&&` between commands | PS 5.1 — use `;` separators. |
| OneDrive sync locks a file mid-run ("file in use") | Exclude the repo from active sync or pause it during test runs. |
| Port 8000/3000 already in use | `Get-NetTCPConnection -LocalPort 8000` → stop the owning process or change `BACKEND_PORT` + `NEXT_PUBLIC_API_BASE_URL`. |
