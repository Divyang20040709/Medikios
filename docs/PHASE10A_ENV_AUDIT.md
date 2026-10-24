# Phase 10A — Final Environment Audit + Safe Repository Preparation

**Audit date:** 23 October 2026
**Scope:** `.env` correctness against application code, plus approved repository-preparation work. No Git
initialisation, no commits, no pushes, no deletions.
**Companion document:** `docs/PHASE10_GIT_SAFETY_REPORT.md` (Phase 10 — Git safety and backup audit).

> **Secret-handling note.** No secret value is reproduced anywhere in this report. Secrets are identified
> only by variable name and source location. The literal `REDACTED` means "a real value exists here and I
> am deliberately not printing it".

---

## 1. Executive summary

**Environment status: WORKING — 1 WARNING requiring a decision, 0 FAILS.**

The `.env` file is functionally correct for free local development. Every capability the application needs
at startup was verified live rather than inferred:

| Capability | Verified evidence |
|---|---|
| Local PostgreSQL | `/health` → `connected: true`, `fallback_in_use: false`; `/api/health/diagnostics` → `active_backend: postgresql` |
| Local Ollama LLM | `/api/tags` lists `llama3.2:latest`; direct `/api/chat` returned a completion |
| Whisper ASR | `model/whisper/base.pt` present (138.5 MB); `/api/speech/status` → `en`/`hi`/`gu` all `ready: true` |
| PaddleOCR | `model/paddleocr/` present with `_pipelines/` |
| JWT signing | `JWT_SECRET` is a strong random value, not the built-in default (startup guard did not fire) |

**Repository status: SAFE-TO-PROCEED, with code-level follow-ups still open.**

`.gitignore` now covers every large, generated and sensitive asset identified in Phase 10, and
`.env.example` no longer contains literal-looking secrets. The two hardcoded secret defaults in
`backend/app/core/config.py` and the `docker-compose.yml` `JWT_SECRET` fallback were **not** changed —
application code is out of scope for this phase — and remain the main blocker to a public push.

**No critical security issue remains that would be made worse by a push**, because nothing has been
initialised or published. Once §7 items C1 and C2 are fixed, the repository is genuinely GitHub-ready.

---

## 2. Configuration audit by group

### 2.1 Database — WARNING (works; one variable is misleading)

`.env` sets `DATABASE_URL` = `postgresql://postgres:REDACTED@localhost:5432/Medikios`.

Resolution order in code:

- `config.py:189-205` (`_raw_db_url`) — `DATABASE_URL` is the first alias checked, so it is the one in use.
  `NEON_DATABASE_URL` is **not set** in `.env` (it appears only in `.env.example`).
- `config.py:152-186` (`_split_db_url`) — splits credentials at the **last** `@`, so the `@` inside the
  password is parsed correctly (`postgres` / `<user>@2004`). This is the behaviour the live connection
  confirms.
- `config.py:231-256` (`database_url`) — **only the username and password are taken from the URL.** Host,
  port and database name come from `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB`, none of which are set
  in `.env`, so the defaults apply: `127.0.0.1`, `5432`, `medikiosk_db`.

**Consequence:** the `Medikios` database name and the `localhost` host in `DATABASE_URL` are **silently
ignored**. The application really connects to `127.0.0.1:5432/medikiosk_db`, confirmed by
`/api/health/diagnostics`:

```
connection: postgresql+asyncpg://postgres:****@127.0.0.1:5432/medikiosk_db
connected: true   fallback_in_use: false   last_error: null
```

This is a WARNING, not a FAIL: the app reaches a real PostgreSQL and never touches the SQLite fallback
(`session.py:127-156`). But a maintainer editing `DATABASE_URL` to point at a different database would see
no effect, which is a genuine operational trap. Fix in Phase 10B (§7 D1).

`session.py:89-116` also runs `Base.metadata.create_all` and additive
`ALTER TABLE users ADD COLUMN IF NOT EXISTS …` at startup. That is schema-level self-healing, not a data
migration; it does not rewrite or delete stored rows.

### 2.2 JWT / session secrets — PASS (with a code-level security finding)

| Variable | State | Consumer |
|---|---|---|
| `JWT_SECRET` | Set to a 64-char URL-safe random value (`REDACTED`) | `auth_router.py:47` encode, `:53` decode |
| `JWT_ALGORITHM` | `HS256` | `auth_router.py:47,53` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` (8 h) | token expiry |
| `NEON_AUTH_URL` | `https://auth.neon.tech` | `config.py:124-136` `effective_auth_url` — **no functional consumer found** |
| `NEON_AUTH_COOKIE_SECRET` | Set (`REDACTED`) | **No consumer anywhere in `backend/`** — declared at `config.py:45`, never read |

The insecure-default guard at `main.py:29-31` compares `JWT_SECRET` against the built-in development
default. Because `.env` supplies a real random value, the guard does not fire — correct behaviour.

**Security finding (code, not `.env`):** `config.py:45-46` ship literal defaults for
`NEON_AUTH_COOKIE_SECRET` and `JWT_SECRET`, and `docker-compose.yml:16` repeats
`${JWT_SECRET:-<the same default>}`. Anyone running the compose stack without exporting `JWT_SECRET`
authenticates with a key that is visible in the source tree. `config.py:27` even states credentials are
"NEVER hardcoded in source", which these two lines contradict. Out of scope here; recorded as §7 C1.

### 2.3 Local LLM (Ollama) — PASS

`LOCAL_LLM_ENABLED=true`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`, `OLLAMA_MODEL=llama3.2`,
`LLM_TIMEOUT_SECONDS=20`.

Verified end-to-end against the code path, not just the settings:

1. `GET /api/tags` returned `llama3.2:latest`.
2. `local_llm.py:88-94` matches either an exact name or the `:`-prefix, so `llama3.2` resolves against
   `llama3.2:latest` → probe returns flavour `"ollama"`.
3. A direct `POST /api/chat` against Ollama returned a non-empty completion → inference genuinely works.

**Actual provider selection and fallback behaviour** (`llm_service.py:155-228`):

- `chat_completion` tries `LocalLLMClient().chat(...)` first; a hit returns `engine="local"`.
- Only if local returns `None` does it consider OpenRouter (`:188`), and only if a key exists.
- Otherwise it returns `engine="deterministic_fallback"` (`:223-228`).
- `local_llm.py:17-19` never raises: connection errors, timeouts and malformed responses all return `None`,
  so a stopped Ollama server degrades the UI honestly instead of breaking it.
- Availability is cached for 60 s (`local_llm.py:34`), so a cold kiosk does not re-probe every turn.
- `followup_service.py:243-273` also uses `LocalLLMClient`, tagging its source `local_llm`.

**Important limitation — WARNING.** `generate_clinical_summary` (`llm_service.py:21-115`) does **not** use
`LocalLLMClient`. It branches solely on `self.api_key` (OpenRouter); with a blank key it prints
"`OPENROUTER_API_KEY` is not set … Engaging clinical deterministic fallback" (`:111`) and builds the summary
from deterministic expert rules (`:113-115`). So on this configuration:

| Feature | Engine actually used |
|---|---|
| AI chat assistant | **Local Ollama `llama3.2`** |
| Follow-up question generation | **Local Ollama `llama3.2`** |
| Clinical summary for the doctor | **Deterministic rules — not Ollama** |

No application-code change is required for the app to start or for chat to work, so nothing is blocked.
Wiring the local LLM into summary generation is a **decision requiring approval** (§7 D1) because it changes
clinically-reviewed output behaviour, and Phase 9 established that summary provenance must be labelled
truthfully.

### 2.4 OpenRouter — PASS (intentionally disabled)

`OPENROUTER_API_KEY=` is blank → `config.py:106-122` `effective_openrouter_key` returns `""` →
`is_openrouter_configured` false. Diagnostics confirm `configured: false`, `key_status: NOT_CONFIGURED`.
`OPENROUTER_MODEL` (`nvidia/nemotron-…`) and `OPENROUTER_BASE_URL` are therefore cosmetic — never sent
anywhere. This is correct for free local development and is a **required** value only if a hosted model is
wanted. Free alternative already in place: Ollama (§2.3).

### 2.5 Speech — PASS

`SPEECH_PROVIDER=auto`, `WHISPER_MODEL_PATH=model/whisper`, `WHISPER_MODEL_SIZE=base`,
`WHISPER_DEVICE=cpu`.

- `provider.py:46` reads `WHISPER_DEVICE` (default `cpu`); `:56-60` loads with
  `download_root=WHISPER_MODEL_PATH`.
- `whisper_model_ready()` (`provider.py:184-201`) is a non-downloading existence check against the same
  root. `model/whisper/base.pt` exists (138.5 MB) → ready.
- `/api/speech/status` live result: `configured_provider: auto`, `en`/`hi`/`gu` → provider `whisper`,
  `ready: true`, `any_backend_ready: true`.
- `auto` + Indic behaviour (`provider.py:215-243`): with Whisper weights present on a CPU host,
  `_indicconformer_preferred` returns False, so `hi`/`gu` also use Whisper. The 2.4 GB IndicConformer
  checkpoint (`indicconformer_stt_multi_hybrid_rnnt_600m.nemo`) is only selected when
  `INDICCONFORMER_DEVICE=cuda` or Whisper is missing. Note `INDICCONFORMER_DEVICE` is **not** set in `.env`
  (defaults to `cpu`).
- Graceful degradation is honest: if the model cannot load, `transcribe` returns
  `provider="whisper_unavailable"` with an empty transcript (`provider.py:109-121`) rather than fabricating
  text.
- `BHASHINI_API_KEY` / `BHASHINI_USER_ID` / `BHASHINI_PIPELINE_ID` are blank and genuinely optional — the
  Bhashini provider only redirects to Whisper (`provider.py:182`).
- The dedicated speech environment `.venv_speech/` exists (54,418 files).

### 2.6 OCR — PASS (configuration), runtime NOT VERIFIED

`OCR_PROVIDER=paddleocr`, `PADDLEOCR_MODEL_PATH=model/paddleocr`, `TESSERACT_PATH=` blank,
`MAX_DOCUMENT_UPLOAD_MB=25`, `OCR_TIMEOUT_SECONDS=90`.

- Model directory present with `_pipelines/`.
- `document_router.py:71,80` enforces the 25 MB limit; `:110` applies the 90 s timeout.
- `TESSERACT_PATH` is optional — consulted only when `OCR_PROVIDER=tesseract`.
- **Not verified:** actually running an OCR job would upload a document and create database rows, which this
  phase forbids. Prior phases record a PaddleOCR engine quirk (mkldnn must be disabled), so treat first-run
  OCR on a fresh machine as untested here.

### 2.7 Qdrant — UNUSED

`QDRANT_URL` and `QDRANT_API_KEY` are blank and **no code anywhere reads them**. This matches the project
decision to reject embedding-based retrieval; the retrieval-stack import ban is enforced by guard tests.
Leaving them blank is correct; deleting them from both env files is optional cleanup (§7 D3).

### 2.8 ABDM — PASS (sandbox, credentials optional)

`ABDM_CLIENT_ID` / `ABDM_CLIENT_SECRET` blank, `ABDM_BRIDGE_URL=https://dev.abdm.gov.in/gateway`,
`ABDM_MODE=sandbox`. Reported by `/health` (`main.py:101`) and diagnostics (`:143`). Blank credentials mean
no live ABDM gateway calls — expected for offline development.

### 2.9 CORS, frontend URL, debug — PASS (two unused keys)

- `BACKEND_CORS_ORIGINS` is consumed via `config.py:138-140` → `main.py:46-54`; when no wildcard is present
  the code also appends `localhost:3000`, `127.0.0.1:3000`, `localhost:8000`. Working as intended.
- `APP_ENV=development`, `DEBUG=True` are declared in `Settings` but **no consumer reads
  `settings.DEBUG` or `settings.APP_ENV`** — inert today, harmless, worth knowing before a production push.
- `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` has **no consumer in `frontend/`**. The frontend calls
  relative `/api/*` and Next rewrites proxy to `127.0.0.1:8000`, so the variable is unused.
- `BACKEND_PORT=8000` is unused too — `Settings` exposes `PORT`, which `.env` does not set. Uvicorn is
  launched manually, so the key has no effect.

---

## 3. Variable classification

**Required for the intended local setup**
- `DATABASE_URL` (or `POSTGRES_USER`/`POSTGRES_PASSWORD`) — without it the app silently degrades to SQLite.
- `JWT_SECRET` — a default exists but is insecure; must be set for anything beyond a throwaway run.

**Optional — blank is a supported configuration**
- `OPENROUTER_API_KEY` (+ `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`) — hosted LLM only.
- `BHASHINI_API_KEY`, `BHASHINI_USER_ID`, `BHASHINI_PIPELINE_ID` — hosted ASR only.
- `TESSERACT_PATH` — only if `OCR_PROVIDER=tesseract`.
- `ABDM_CLIENT_ID`, `ABDM_CLIENT_SECRET` — live ABDM sandbox/satellite only.
- `LOCAL_LLM_ENABLED`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `LLM_TIMEOUT_SECONDS` — degrade gracefully to
  deterministic fallback when Ollama is not running.

**Unused by any code path**
- `NEON_AUTH_COOKIE_SECRET`, `NEON_AUTH_URL`, `QDRANT_URL`, `QDRANT_API_KEY`,
  `NEXT_PUBLIC_API_BASE_URL`, `BACKEND_PORT`, `APP_ENV`, `DEBUG`.

**Insecure as configured elsewhere (code, not `.env`)**
- `config.py:45-46` default `JWT_SECRET` / `NEON_AUTH_COOKIE_SECRET`.
- `docker-compose.yml:16` `JWT_SECRET` fallback default.

---

## 4. Missing files, dependencies and model paths

**Nothing required for startup is missing.** Measured on disk:

| Path | State |
|---|---|
| `model/whisper/base.pt` | Present, 138.5 MB |
| `model/paddleocr/` | Present (165 files across `model/`) |
| `indicconformer_stt_multi_hybrid_rnnt_600m.nemo` | Present, 2 403 MB (optional, CPU-slow) |
| `.venv_speech/` | Present, 5 098 MB / 54 418 files |
| Ollama server + `llama3.2` | Reachable, model pulled |
| Local PostgreSQL `medikiosk_db` | Connected, schema present |
| `backend/data/` | Absent (referenced only as a compose volume mount) |
| `.git` | Absent — project is not a repository |

Feature impact if something were removed: no model → honest "unavailable" transcripts; no Ollama →
deterministic chat fallback; no PostgreSQL → SQLite fallback with a visible warning in `/health`. None of
these prevent startup.

---

## 5. Free / local alternatives for paid or hosted services

| Hosted service | Status here | Free local equivalent already working |
|---|---|---|
| OpenRouter / NVIDIA Nemotron | Disabled (blank key) | Ollama `llama3.2` for chat and follow-ups |
| Neon managed PostgreSQL | Not used | Local PostgreSQL `medikiosk_db` |
| Neon Auth | Not implemented in code | Local JWT (`auth_router.py`) |
| Bhashini STT | Blank credentials | Whisper `base` on CPU |
| IndicConformer on GPU | CPU-only host | Whisper for `en`/`hi`/`gu` |
| Qdrant vector DB | Unused | Keyword/ontology retrieval (current design) |
| Tesseract OCR | Not selected | Local PaddleOCR |
| ABDM sandbox gateway | Sandbox, no credentials | Local FHIR serializers |

---

## 6. Repository preparation performed (approved edits only)

### 6.1 `.gitignore` — additive, existing rules preserved

Newly covered (previously unprotected):

```
.env.*                + !.env.example   (catch .env.production etc., keep the template tracked)
.venv_speech/  **/.venv_speech/         (5 098 MB — was NOT matched by .venv/)
/model/                                 (142 MB weights + vendored whisper/paddleocr)
/datasets/                              (668 MB IndicVoices / MedDialog / Synthea)
*.nemo  *.pt  *.pth  *.joblib  *.onnx  *.safetensors
frontend/.next_stale_qa/  **/.next_stale_qa/   (103 MB stale QA build output)
*.tsbuildinfo
backend/data/
/medikiosk.db  /backend/medikiosk.db
```

Already present and left untouched: `.env`, `*.pem`, `*.key`, `__pycache__/`, `.venv/`, `*.db`,
`*.sqlite3`, `.pytest_cache/`, `scratch/`, `backend/uploads/*` (with `!.gitkeep`), `node_modules/`,
`.next/`, `out/`, `build/`, `*.log`, IDE/OS files.

Every large asset stays **on disk** — nothing was deleted, moved or renamed.

### 6.2 `.env.example` — placeholders only

`NEON_AUTH_COOKIE_SECRET` and `JWT_SECRET` previously carried literal-looking secret values identical to the
insecure code defaults. Both are now `__CHANGE_ME_GENERATE_A_RANDOM_SECRET__`, with a comment showing how to
generate one. **No value was copied from `.env`** — the real values differ and remain only in `.env`.
`NEON_DATABASE_URL` keeps its obvious `user:password@ep-sample-12345…` sample form.

### 6.3 Application code — deliberately not modified

`backend/app/core/config.py`, `docker-compose.yml` and all other source files were left exactly as found, per
the phase rules. Required follow-ups are documented in §7.

---

## 7. Exact fixes needed before this is considered safe to publish

**Code (needs approval — outside this phase's edit scope)**
- **C1** Remove the literal defaults at `config.py:45-46`; make `JWT_SECRET` mandatory at startup (fail
  closed) instead of warning. `NEON_AUTH_COOKIE_SECRET` should be deleted outright, since nothing reads it.
- **C2** `docker-compose.yml:16` — drop the `:-<default>` fallback so compose fails without a real
  `JWT_SECRET`.
- **C3** Optional: add `DATABASE_URL` to the compose environment block; compose currently cannot express the
  local-PostgreSQL setup that `.env` uses.

**Configuration decisions (needs approval)**
- **D1** Decide whether `generate_clinical_summary` should route through the local LLM. Today only chat and
  follow-ups do. Any change must keep the Phase 9 provenance labelling truthful.
- **D2** Decide the intended database name. Either set `POSTGRES_DB=Medikios` in `.env`, or rename
  `DATABASE_URL`'s trailing segment to `medikiosk_db` so the URL stops lying about where data goes.
- **D3** Remove unused keys (`QDRANT_*`, `NEON_AUTH_*`, `NEXT_PUBLIC_API_BASE_URL`, `BACKEND_PORT`) or
  annotate them as reserved, so `.env.example` documents only real knobs.

**Verification still outstanding**
- **V1** First-run OCR on a clean machine (PaddleOCR engine initialisation) — not exercised this phase.
- **V2** Voice transcription through the kiosk UI end-to-end with a real recording.

---

## 8. Checks performed and results

| # | Check | Result |
|---|---|---|
| 1 | `.env` parsed against `config.py` resolution order | PASS — `DATABASE_URL` is the effective alias, credentials split at last `@` |
| 2 | Live DB backend (`/health`, `/api/health/diagnostics`) | PASS — `postgresql`, `connected: true`, `fallback_in_use: false` |
| 3 | DB name/host actually used | WARNING — `127.0.0.1:5432/medikiosk_db`, not the URL's `localhost/…/Medikios` |
| 4 | `JWT_SECRET` is not the insecure default | PASS — `main.py:29` guard silent |
| 5 | Ollama reachable + model present | PASS — `/api/tags` → `llama3.2:latest` |
| 6 | Ollama probe/matching logic | PASS — `local_llm.py:88-94` prefix match |
| 7 | Local LLM inference actually returns text | PASS — direct `/api/chat` non-empty |
| 8 | OpenRouter disabled with blank key | PASS — `key_status: NOT_CONFIGURED` |
| 9 | Whisper weights present + readiness | PASS — `base.pt` 138.5 MB; `en`/`hi`/`gu` all `ready` |
| 10 | PaddleOCR model directory present | PASS — `_pipelines/` exists |
| 11 | OCR runtime execution | NOT VERIFIED — would create DB rows / uploads |
| 12 | Qdrant / Neon-auth / `NEXT_PUBLIC_API_BASE_URL` consumers | CONFIRMED UNUSED (repo-wide search) |
| 13 | `.git` existence | NO REPOSITORY — as expected; none created |
| 14 | Tracked / staged secret scan | SKIPPED — requires a repository; `git init` prohibited this phase |
| 15 | `git check-ignore` dry run | SKIPPED — requires `git init`; rules verified statically by pattern matching instead |
| 16 | `.env.example` free of literal secrets | PASS — 0 occurrences of the previous literals; both secrets now `__CHANGE_ME__` |
| 17 | Real `.env` values copied into `.env.example` | PASS — none copied |
| 18 | Automated test suite | SKIPPED — see note below |
| 19 | Large assets still on disk | PASS — `.venv_speech` 5 098 MB, `datasets` 668 MB, `model` 142 MB, `.nemo` 2 403 MB, `.next_stale_qa` 103 MB all intact |
| 20 | Deletions / moves of user files | NONE |

**Note on check 18 (tests skipped).** The existing pytest suite is not read-only: it exercises registration,
intake and encounter-signing paths against the **live** PostgreSQL `medikiosk_db`, and
`session.py:init_db()` runs `create_all` plus additive `ALTER TABLE` on import. Running it would create or
mutate persistent rows, which this phase explicitly forbids. It was therefore skipped deliberately rather
than reported as passing. The last full green run remains recorded in `docs/QA_FIX_REPORT.md`
(213 passed / 1 skipped).

---

## 9. Files changed

| File | Change |
|---|---|
| `.gitignore` | +22 lines of ignore rules (additive; nothing removed) |
| `.env.example` | 2 literal secret values → placeholders, +2 explanatory comment lines |
| `docs/PHASE10A_ENV_AUDIT.md` | New — this report |

**Not changed:** `.env`, any application code, `docker-compose.yml`, database contents, user accounts, model
assets, datasets, QA artifacts, `docs/PHASE10_GIT_SAFETY_REPORT.md`.

---

## 10. Assumptions, limitations and what remains unverified

- Ignore-rule correctness was established by **static pattern matching**, not by `git check-ignore`, because
  that needs a repository and `git init` is prohibited. The patterns used are ordinary gitignore syntax
  (leading `/` = repo-root anchored, trailing `/` = directory, `!` = negation), and `!.env.example` appears
  after `.env.*`, so the negation is not shadowed by ordering.
- "Ignored" only becomes meaningful at `git init` time. Since the project has never been a repository,
  **nothing is currently tracked**, so there is no possibility that an already-committed secret escapes the
  new rules. This must be re-checked with `git ls-files` immediately after Phase 10B initialises the repo.
- Secrets were verified to exist and to be consumed, never printed. Their **strength** was not assessed
  beyond confirming they are not the known insecure defaults.
- OCR and voice were validated at the configuration and file-existence level; live inference for those two
  paths is not covered by this phase (V1, V2).
- OneDrive is live file sync, not a versioned backup; the backup recommendation in the Phase 10 report still
  stands unaddressed.

---

## 11. Actions requiring explicit approval before Phase 10B

1. Apply C1 — remove hardcoded secret defaults in `config.py`, make `JWT_SECRET` fail closed.
2. Apply C2 — remove the `JWT_SECRET` fallback in `docker-compose.yml`.
3. Decide D1 — route clinical-summary generation through the local LLM or keep deterministic rules.
4. Decide D2 — reconcile the `DATABASE_URL` database name with `POSTGRES_DB`.
5. Decide D3 — prune or annotate unused environment keys.
6. Run `git init`, then immediately `git ls-files` to confirm no secret, model, dataset or venv path is
   staged, before any remote is added or pushed.
7. Rotate `JWT_SECRET` and `NEON_AUTH_COOKIE_SECRET` if this machine has ever been shared or backed up
   publicly.
