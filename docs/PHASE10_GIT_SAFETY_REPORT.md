# MediKiosk — Phase 10: Git Safety & Backup Report (AUDIT ONLY)

**Mode:** Read-only audit. No source, config, `.gitignore`, `.env`, database, or dependency was modified.
No `git init`, commit, push, remote change, publish, or file deletion was performed. No secret value or
patient record content is reproduced in this report.

**Audit date:** 2026-10-23
**Auditor:** Senior DevOps / Security review (agent-driven)
**Working directory:** repository root `Medikiosk-main`

---

## 1. Executive Summary

| Area | Verdict | One-line status |
|---|---|---|
| Git repository present | **NO — NOT A REPO** | No `.git`; `git rev-parse` returns `fatal: not a git repository`. Git 2.56.0 is installed but the project is uninitialized. |
| Tracked secrets in history | **NOT VERIFIED (moot)** | There is no history/HEAD to scan. Nothing is tracked yet, so no secret is currently committed. Risk is prospective (first `git add .`). |
| `.gitignore` — named secrets (`.env`, `*.db`, uploads, `node_modules`, `.next`, caches) | **PASS** | Correctly ignores `.env`, `*.db`/`*.sqlite3`, `backend/uploads/*`, `node_modules/`, `.next/`, `__pycache__`, `.pytest_cache`, `scratch/`. |
| `.gitignore` — environment & large/data paths | **FAIL** | Does **not** ignore `.venv_speech/` (~5.0 GB), `model/` (142 MB), `datasets/` (667 MB incl. simulated patient CSVs), the 2.35 GB `.nemo` file, or `frontend/.next_stale_qa` (102 MB). |
| Hardcoded default secrets in version-control-eligible files | **WARNING/FAIL** | Literal default secret strings exist in `backend/app/core/config.py` (`JWT_SECRET`, `NEON_AUTH_COOKIE_SECRET`) and `docker-compose.yml` (`JWT_SECRET` fallback). Values redacted here. |
| `.env.example` hygiene | **WARNING** | Placeholders present and API keys empty (good), but two secret example values are filled-in literals rather than obvious `CHANGE_ME` tokens. |
| Backup existence | **NOT VERIFIED / LIKELY NONE** | No backup mechanism inspected beyond OneDrive folder sync; no git remote, no DB dump. A dedicated backup plan is required. |
| GitHub-readiness | **FAIL (currently un-pushable safely)** | Multiple files exceed GitHub limits (100 MB warning / 1 GB hard block); ~6 GB+ of non-ignored binary/data would enter the first commit. |

**Bottom line:** The single most dangerous state is that the project is **not under version control at all**
(no local history, no remote, no rollback). The `.gitignore` correctly protects the *named* secrets
(`.env`, databases, uploads) but leaves large model/venv/dataset artifacts unprotected, and a small number
of **hardcoded default secret literals** sit in files that would normally be committed. Initializing Git
without first fixing the ignore rules would create a huge, partly-sensitive, and non-pushable repository.

---

## 2. Actual Repository Status (verified)

Evidence (read-only commands, run at repo root):

```
$ Get-ChildItem -Force -Directory -Filter ".git"      -> (no output: no .git directory)
$ git rev-parse --is-inside-work-tree                 -> fatal: not a git repository (or any of the parent directories): .git
$ git status                                          -> fatal: not a git repository (or any of the parent directories): .git
$ git --version                                       -> git version 2.56.0.windows.2
```

Findings:
- **Git is NOT initialized** in the project or any parent directory. **PASS-verified** (confirmed by command).
- Consequently: **no branch, no HEAD, no commit metadata, no remotes, no staged/unstaged state, no tracked
  or untracked file lists** exist. These cannot be reported because the repository does not exist. Labeled
  **N/A (no repo)** rather than assumed empty.
- **Nothing is currently tracked**, therefore **nothing sensitive is currently committed**. The
  `.gitignore` rules are **prospective protection only** — they take effect on the first `git add` after a
  future `git init`. (This distinction is required by audit rule #10.)
- The workspace lives under **OneDrive** (`OneDrive\Desktop\...`), which is a *file-sync copy, not a version
  control system* and not an offline-safe backup (see §7). OneDrive sync state for large binaries is also
  relevant to the `EINVAL readlink` build failures noted in earlier QA phases.

---

## 3. `.gitignore` Assessment (verified against actual paths)

`.gitignore` is 51 lines. Categories checked against files that actually exist on disk:

| Protection target | Pattern in `.gitignore` | Present on disk? | Matched? | Verdict |
|---|---|---|---|---|
| `.env` | `.env`, `.env.local`, `.env.*.local`, `*.env` | Yes (`.env`, 2 KB) | Yes | **PASS** |
| Key material | `*.pem`, `*.key` | No such files found | n/a | PASS (defensive) |
| Python caches | `__pycache__/`, `*.py[cod]`, `.pytest_cache/` | Yes | Yes | **PASS** |
| Python venvs | `.venv/`, `**/.venv/`, `env/`, `venv/`, `backend/.venv/` | **`.venv_speech/` exists (~5.0 GB, 54,418 files)** | **No** (`venv_speech` ≠ `venv`/`.venv`) | **FAIL** |
| Local DB files | `*.db`, `*.sqlite3` | Yes: `medikiosk.db` (184 KB), `backend/medikiosk.db` | Yes | **PASS** |
| Node/Next build | `node_modules/`, `.next/`, `**/.next/`, `out/`, `build/` | Yes | Yes | **PASS** |
| Stale Next dir | (no pattern for `.next_stale_qa/`) | Yes (`frontend/.next_stale_qa/`, 102 MB, 67 files) | **No** | **FAIL** |
| QA scratch | `scratch/` | Yes (screenshots, probes, `qa_big.wav` 16 MB) | Yes | **PASS** |
| Uploaded documents | `backend/uploads/*` + `!backend/uploads/.gitkeep` | Yes (140 files ≈ 0.2 MB, prescription images) | Yes (contents ignored) | **PASS** (with note) |
| Logs | `*.log`, `npm-debug.log*`, etc. | — | Yes | PASS |
| IDE/OS | `.vscode/`, `.idea/`, `.DS_Store`, `Thumbs.db` | — | Yes | PASS |

Notes / gaps:
- **Model weights / datasets are ignored only because they are *inside* `scratch/`-style or `.db` patterns —
  they are NOT.** `model/` (142 MB) and `datasets/` (667 MB) are **not matched by any rule** and would be
  committed.
- **`datasets/synthea/*.csv`** and `datasets/med_dialog`, `datasets/indic_voices` contain (simulated)
  patient/clinical records and speech corpora. Even synthetic, this is bulk clinical-like data plus a very
  large tree that has no place in a normal source repo. **FAIL.**
- **`indicconformer_stt_multi_hybrid_rnnt_600m.nemo` (2,403 MB) at root** is unmatched → would be committed
  and cannot be pushed to GitHub (see §8). **FAIL.**
- The uploads negation references `backend/uploads/.gitkeep` which **does not exist** on disk (verified
  `Test-Path` → `False`), so the uploads folder would vanish from version control entirely once emptied;
  minor structural issue, contents are still protected.

---

## 4. Sensitive-File & Secret-Scan Findings (values redacted)

**Scan method (safe/read-only):** filename-only heuristic across source, config, docs, and manifests for
patterns `api_key=`, `secret=`, `password=`, `postgresql…://user:pass@`, and `Bearer <token>`. **Matching
lines and values were NOT printed**; only file paths + match counts were captured, then the two most
security-relevant files (`config.py`, `docker-compose.yml`) were inspected to classify each hit. This is a
heuristic scan and does **not** prove the absence of secrets (audit rule #10).

Files flagged by the heuristic (path : approximate match count):
`backend/app/core/config.py` (3) · `docker-compose.yml` (2) · `backend/app/api/doctor_router.py` (4) ·
`backend/app/api/{admin,auth}_router.py` (1 each) · `backend/app/main.py` (1) ·
`backend/tests/*` (multiple, 1–3 each) · `docs/*` and `ARCHITECTURE_AND_IMPLEMENTATION.md` (report text) ·
`frontend/.next_stale_qa/**` (bundled build JS).

Classified findings:

| # | Location | Type | Assessment | Severity |
|---|---|---|---|---|
| S-1 | `backend/app/core/config.py` — `JWT_SECRET` | Hardcoded default **literal** secret in source | Real value present (redacted). Used whenever `.env` does not override it. Would be committed. | **FAIL** (High) |
| S-2 | `backend/app/core/config.py` — `NEON_AUTH_COOKIE_SECRET` | Hardcoded default **literal** secret in source | Real value present (redacted). Would be committed. | **FAIL** (High) |
| S-3 | `docker-compose.yml` — `JWT_SECRET=${JWT_SECRET:-<literal>}` | Insecure **default fallback** secret embedded in a committed manifest | Redundant insecure default; copies S-1 into infra file. | **WARNING** (Med) |
| S-4 | `config.py` — `safe_database_url` f-string `…:****@…` | Benign | Credential-**masking** template, not a secret. `POSTGRES_USER/PASSWORD` default to empty (read from `.env` only). | **PASS** |
| S-5 | `config.py` / `.env.example` — `NEON_DATABASE_URL=postgresql+asyncpg://user:password@…sample…` | Placeholder only | Sample/placeholder creds, not real. | **PASS** |
| S-6 | `backend/app/api/*_router.py`, `main.py` hits | Benign references | `password=`/`Bearer` are function kwargs / header-name references (e.g., bearer scheme), not literal secrets. Verified by pattern context. | **PASS** (contextual) |
| S-7 | `backend/tests/*` hits | Benign | Test fixtures referencing `password=`/`api_key=` parameter names and `.env` fallback logic; no production credential literals observed. | **PASS** (contextual) |
| S-8 | `docs/*`, `ARCHITECTURE_AND_IMPLEMENTATION.md` | Documentation text | Mentions masked connection strings (`postgres:****@`) and policy language. | **PASS** |
| S-9 | `frontend/.next_stale_qa/**` | Stale build artifact bundling client auth code | Contains minified JS with `Bearer` string; this is **generated output that should not be tracked** (see G-gap). | **WARNING** (Med) |
| S-10 | `.env` (real secrets file) | Sensitive **by design** | Exists (2 KB). Correctly ignored by `.gitignore` (`.env`). Not read/opened during this audit. | **PASS** (ignored) |

**Conclusion:** No secret is currently committed (no repo). But S-1/S-2/S-3 are **hardcoded secret defaults in
files that would be tracked**, and must be replaced with env-only loading + placeholder defaults before any
repository is created. S-10 and the `.db`/`uploads` files are protected by name, but that protection only
bites at first `git add`.

---

## 5. Tracked vs. Untracked Risk

- **Tracked files: NONE.** There is no Git index/HEAD (**N/A — no repository**). Therefore all files are
  effectively untracked and none are in any history.
- Because nothing is tracked yet, the usual "already-tracked despite ignore rule" hazard does **not** apply
  at this moment (verified: no `.git`). This is a genuine advantage — the repository can be created
  correctly from scratch.
- The **prospective** risk profile at first `git add .` (given the current `.gitignore`) is:

| Would be correctly excluded | Would be WRONGLY included (not ignored) |
|---|---|
| `.env`, `medikiosk.db`, `backend/medikiosk.db`, `backend/uploads/*`, `node_modules`, `.next`, `__pycache__`, `.pytest_cache`, `scratch/` | **`.venv_speech/` (~5.0 GB)**, **`model/` (142 MB)**, **`datasets/` (667 MB, patient-like CSVs)**, **`indicconformer…nemo` (2.35 GB)**, **`frontend/.next_stale_qa/` (102 MB)**, plus hardcoded-secret literals in `config.py` / `docker-compose.yml` |

Total wrongly-includable payload ≈ **8+ GB** across ~55k files, several of which break GitHub limits (§8).
**Verdict: FAIL** for a naive first commit; **PASS** for the named-secret exclusions.

---

## 6. `.env.example` Assessment (verified)

- 61 lines. Covers DB, auth/JWT, OpenRouter, local LLM/Ollama, speech, OCR, Qdrant, ABDM/FHIR, ports.
- **Real service credentials are empty or placeholder** — e.g. `OPENROUTER_API_KEY=`, `BHASHINI_API_KEY=`,
  `QDRANT_API_KEY=`, `ABDM_CLIENT_SECRET=` (blank), and `NEON_DATABASE_URL` uses `user:password@…sample…`.
  This is the desired behavior. **PASS.**
- **Hygiene WARNING:** `NEON_AUTH_COOKIE_SECRET` and `JWT_SECRET` are populated with realistic-looking
  literal strings instead of unmistakable `CHANGE_ME` placeholders, and the *same* literals appear as defaults
  in `config.py`/`docker-compose.yml`. If a deployer copies `.env.example`→`.env` without editing, the app
  runs on publicly-known signing secrets. Recommend replacing both with explicit placeholder tokens.

---

## 7. Backup Status & Recommended Procedure (no backup performed)

**Current state — NOT VERIFIED / effectively NONE for recoverable version history:**
- No Git remote (no repo). No `.git` means no local commit history to recover from.
- The folder is inside **OneDrive**, which provides file versioning/sync but is **not** a safe project
  backup: it syncs the live working tree (including `.env` and DB files) and has no controlled, secret-free
  restore point; large-binary sync is also a known source of the `EINVAL readlink` build failures.
- No database dump/export observed. PostgreSQL runs live; `medikiosk.db`/`backend/medikiosk.db` SQLite files
  are dev-only.

**Recommended backup procedure (PLAN ONLY — to be executed later with approval):**
1. **Source:** Once (and only once) the ignore gaps in §3/§5 are fixed, create a **private** Git repository
   and push to a private remote. Git is the primary backup of *source* — secret-free by construction.
2. **Secrets store:** Keep `.env` **out of Git**. Back it up via a secrets manager (or an encrypted
   container: `age`/`gpg`/OS keychain, or a password manager). Never commit, never plain-copy.
3. **Database:** Use logical dumps on a schedule — for PostgreSQL `pg_dump medikiosk_db` to a compressed,
   **encrypted** file; for SQLite `sqlite3 medikiosk.db ".backup …"`. Store dumps **outside** OneDrive/Git.
   Because DBs contain patient data (incl. synthetic QA rows), treat dumps as PHI-equivalent: encrypt at rest,
   restrict access, do not upload to public storage.
4. **Uploads / model artifacts / datasets:** These are large, non-source binaries. Track them via
   **Git LFS** or, better, an artifact store / object storage with its own retention — **not** in the
   source repo. Regenerate/download where possible instead of versioning.
5. **The 2.35 GB `.nemo` model:** Do **not** back it up inside Git at all. Keep a documented download/
   build recipe (name + source + checksum) and store the file itself in object storage or LFS.
6. **Retention/verification:** 3-2-1 pattern (3 copies, 2 media, 1 off-site), periodic restore tests.
   Verify backups actually restore (unverified until a restore is exercised).

---

## 8. GitHub-Readiness Risks

| Risk | Evidence | Consequence | Verdict |
|---|---|---|---|
| Oversized single file | `indicconformer…nemo` = **2,403 MB** | GitHub hard-blocks files > 100 MB on push (rejects > 1 GB); cannot push | **FAIL** |
| Bulk data dir | `datasets/` = **667 MB** (539 files, patient-like CSVs) | Exceeds recommended repo size; privacy exposure of clinical-like data even if synthetic | **FAIL** |
| Virtualenv dir | `.venv_speech/` = **5,098 MB** (54,418 files) | Absurd commit size; OS-specific binaries; breaks clone/CI | **FAIL** |
| Stale build dir | `frontend/.next_stale_qa/` = **102 MB** | > 100 MB files possible; committed generated output | **WARNING** |
| Model weights | `model/` = **142 MB** (165 files) | Large binaries in Git without LFS | **WARNING** |
| Hardcoded secrets committed | `config.py` (S-1/S-2), `docker-compose.yml` (S-3) | Secrets become public on push → immediate rotation needed | **FAIL** |
| `.env`/DB/uploads leak | Protected by name in `.gitignore` | Safe **only if** ignore respected and never force-added | **PASS (conditional)** |
| Public/private exposure of PHI | `datasets/synthea`, uploads | DPDP/PHI risk if repo made public | **FAIL** until excluded |

**Verdict: NOT GitHub-ready as-is.** Before any init/push: extend `.gitignore`, add Git LFS (or object
storage) for models/datasets, remove hardcoded secret defaults, and confirm the uploads/DB/env set stays
ignored.

---

## 9. Prioritized Recommendations

**P0 (blocking, before creating any repository):**
1. Extend `.gitignore` to exclude the environment/data/artifact paths that are currently missed:
   `.venv_speech/`, `model/` (or move to LFS), `datasets/`, `*.nemo`, `frontend/.next_stale_qa/`, and add
   `.venv*/` broadly. *(This is a `.gitignore` edit — requires approval; not done in this audit.)*
2. Remove hardcoded default secrets from `config.py` and `docker-compose.yml`; fail-closed if `JWT_SECRET` /
   `NEON_AUTH_COOKIE_SECRET` are unset in non-dev environments; replace `.env.example` secret literals with
   `CHANGE_ME` placeholders. *(Source edit — requires approval.)*
3. Decide artifact strategy (Git LFS vs. external storage) for the 2.35 GB model, `model/`, and `datasets/`.

**P1 (repository creation, when approved):**
4. `git init` **only after** P0; add a `.gitignore` sanity check (`git status --ignored` review) before the
   first commit; confirm `.env`, `*.db`, `uploads/*`, venvs, model/dataset dirs are **not** staged.
5. Create a **private** remote; run a secret scanner (e.g. `gitleaks`/`trufflehog`) on the staged set before
   the first push (never after a secret has entered history).

**P2 (durability):**
6. Stand up the backup plan in §7 (Git for source; secrets manager for `.env`; encrypted `pg_dump`/SQLite
   backups outside Git/OneDrive; LFS/object store for binaries).
7. Remove or store `frontend/.next_stale_qa/` and other stale artifacts (approval-gated deletion).

**P3 (housekeeping, from prior phases, out of scope here):** SEC-4 demo-credential gating on the login page;
the 900+ pytest warnings; docs/README claims audit.

---

## 10. Actions Requiring Your Approval (this audit performed NONE of them)

- [ ] Edit `.gitignore` (add `.venv_speech/`, `model/`, `datasets/`, `*.nemo`, `.next_stale_qa/`, `.venv*/`).
- [ ] Remove/replace hardcoded secret defaults in `config.py` and `docker-compose.yml`.
- [ ] Replace `.env.example` secret literals with clear placeholders.
- [ ] Run `git init` and create a first commit.
- [ ] Create a remote and push (private).
- [ ] Adopt Git LFS / object storage for models and datasets.
- [ ] Create/execute database backups (PostgreSQL dump / SQLite backup).
- [ ] Delete stale artifacts (`frontend/.next_stale_qa/`, and any `scratch/`/QA files you choose).
- [ ] Rotate any secret that you consider already exposed (JWT/cookie secrets are present as literals in
      source and should be rotated before production use).

---

## 11. Limitations, Assumptions & Verified-vs-Assumed

- **Verified (by command / file read):** absence of `.git`/repo; `.gitignore` contents; existence + sizes of
  `.env`, `*.db`, `model/`, `datasets/`, `.venv_speech/`, `.nemo`, `.next_stale_qa/`, uploads; the
  `.env.example` and `config.py`/`docker-compose.yml` contents inspected for classification.
- **Heuristic / NOT exhaustive:** the secret scan is a keyword/pattern pass, not a cryptographically complete
  audit, and does **not** prove no other secret exists anywhere. Router/test hits were classified as benign
  by pattern context, not by exhaustive manual review of every line.
- **Not verified (no repository to inspect):** branch/commit/remote metadata, tracked-file list, and history
  secrets — these are **N/A because Git is not initialized**, not because they were confirmed safe.
- **Backup existence** is inferred (no remote/no dump observed) rather than fully verified across the whole
  machine/OneDrive account.
- **No ignore rule was "trusted as safe without checking tracking":** since there is no repo, nothing is
  already-tracked; the report states explicitly that protection is prospective only.

**Overall repository-safety status: FAIL (not version-controlled; ignore gaps + hardcoded secret defaults)
— recoverable by P0 fixes before first init.**
