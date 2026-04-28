# Role 2 Exercise Builder

LLM-driven generator for USMC Role 2 (Forward Surgical) medical training exercises. Given a few-day operations plan — tactical settings, casualty volumes, MASCAL / CBRN / detainee toggles, environment, region, threat level — the app produces a downloadable ZIP containing:

- **Case book** (.docx) with detailed Z-MIST, 9-line MEDEVAC, vitals trends, contingencies, and debrief questions per casualty.
- **MSEL** (.xlsx) — minute-by-minute schedule of injects, with assigned evaluators based on the personnel footprint.
- **WARNO**, **Annex Q**, **MEDROE** (.docx) — paragraph-style supporting documents.
- **Generation summary** (.json) — what was requested, what came back, what fell back to template, what errored.

Stack: **FastAPI** (Python async) backend, **Next.js** (TypeScript / Tailwind) frontend, optional **Postgres** for history. Provider-pluggable case generation (Gemini today, Bedrock-ready for GovCloud).

---

## Architecture

```
┌─────────────────────┐       ┌──────────────────────────────┐
│ Next.js (App Router)│       │ FastAPI                      │
│  - / (setup)        │ HTTP  │  - /generate-exercise (sync) │
│  - /tactical        │──────▶│  - /jobs/* (async + polling) │
│  - /history         │       │  - /settings/matrices/*      │
│  - /settings/...    │       │  - /exercises/*              │
└─────────────────────┘       └──────────┬───────────────────┘
                                         │
                              ┌──────────┴───────────┐
                              ▼                      ▼
                     ┌───────────────┐    ┌─────────────────────┐
                     │ CaseProvider  │    │ Postgres (optional) │
                     │  Gemini / stub│    │  exercises          │
                     │  Bedrock(stub)│    │  exercise_jobs      │
                     └───────────────┘    │  matrix_settings    │
                                          └─────────────────────┘
```

Without `DATABASE_URL`, jobs and matrix overrides live in-memory (lost on restart) and exercise history is unavailable; everything else still works.

---

## Quick start (local)

### Prereqs
- Python 3.11+
- Node 20+ (or any version Next.js 15 supports)
- Postgres (optional; skip if you want DB-less mode)

### Setup
```bash
# 1. Clone + env
git clone <this repo>
cd role2-builder
cp .env.example .env          # fill in GEMINI_API_KEY at minimum
                              # set CASE_PROVIDER=stub if you don't have a key

# 2. Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn backend.main:app --reload --port 8000

# 3. Frontend (separate terminal)
npm install
npm run dev                   # http://localhost:3000
```

Open the browser at <http://localhost:3000>, fill in the setup form, and hit **Generate**. Large exercises use the `/jobs/*` async path with progress polling and a cancel button.

### API docs
With the backend running, FastAPI ships an OpenAPI explorer at <http://localhost:8000/docs>. Every endpoint has a tag + description so the explorer is the most up-to-date API reference.

---

## Configuration

All env vars live in [.env.example](./.env.example) with inline guidance. The high-stakes ones:

| Var | Default | Notes |
|---|---|---|
| `CASE_PROVIDER` | `gemini` | `gemini`, `bedrock`, or `stub` (deterministic fake — use in tests) |
| `GEMINI_API_KEY` | _(required for gemini)_ | |
| `DATABASE_URL` | _(unset → DB-less mode)_ | `postgres://` or `postgresql://` both accepted |
| `CASE_BATCH_SIZE` | `5` | Cases per LLM batch |
| `CASE_BATCH_CONCURRENCY` | `3` | In-flight batches per job |
| `LOG_LEVEL` | `INFO` | |
| `LOG_FORMAT` | _(human)_ | Set to `json` for log aggregators |
| `NEXT_PUBLIC_API_URL` | _(prod URL)_ | Where the browser reaches the FastAPI backend |

---

## Tests

```bash
pytest                        # 142 tests, ~5s
pytest -W error::DeprecationWarning   # CI mode — clean
```

Test files live under `backend/tests/`:
- `test_case_generator.py` — provider batch/retry/cancel mechanics
- `test_casualty_planner.py` — example-based tests for `build_day_plan`
- `test_planner_properties.py` — Hypothesis property-based fuzzing
- `test_schedule_builder.py` — minute-by-minute MSEL builder
- `test_matrices.py` — default values and shape guards
- `test_matrix_store.py` — overrides, merge, settings endpoints
- `test_jobs.py` — JobStore CRUD + end-to-end job lifecycle + cancellation
- `test_pipeline_snapshot.py` — `matrix_snapshot` flows through pipeline
- `test_legacy_endpoints.py` — `/generate-exercise`, `/health`, `/generate-name` integration (DB-less paths)
- `test_db_endpoints.py` — `/exercises/*`, `/health` DB ping, job→exercise download, snapshot persistence (SQLite-backed fixture)
- `test_pipeline_integration.py` — planner + generator + schedule together
- `test_providers.py` — provider abstraction contract

Frontend has no tests yet (see _Known gaps_ below).

---

## Project layout

```
backend/
  main.py              FastAPI app + endpoints + pipeline orchestration
  casualty_planner.py  build_day_plan: inputs → per-day EtiologyBuckets + triage_targets
  case_generator.py    Batched + retried + cancellable case generation
  schedule_builder.py  EtiologyBuckets → minute-by-minute MSEL with evaluator assignments
  matrices.py          Default trauma:DNBI ratios, triage distributions, etiology pools
  matrix_store.py      Override / preset persistence + MatrixView merge
  presets.py           Named preset bundles (loaded from preset_data/)
  jobs.py              JobStore (Postgres + InMemory) + global semaphore
  db.py                SQLAlchemy models, optional engine
  logging_config.py    Structured logging + correlation-id LoggerAdapter
  prompts.py           Case generation system prompt
  providers/           Pluggable LLM backends (gemini, bedrock-stub, stub)
  preset_data/*.json   Shipped preset bundles
  tests/               pytest suite

src/app/               Next.js App Router pages
  page.tsx             Setup form (home)
  tactical/page.tsx    Per-day inputs + generate trigger + job polling UI
  history/page.tsx     Past exercises (when DB available)
  settings/matrices/   Matrix configuration editor

docs/
  STRATEGY.md          Original problem inventory + phase plan
  DEVLOG.md            Per-session changelog (read this for context on past decisions)
  FOR_REVIEW_*.md      Documents pending SME / user review
```

---

## Operating notes

- **Job concurrency:** A global `asyncio.Semaphore(1)` serializes job execution. Multiple submissions queue in `status='queued'` until their turn.
- **Cancellation:** Graceful — the worker checks job status between batches; in-flight LLM calls finish (no orphans). Partial work is discarded (no half-saved Exercise row).
- **Matrix overrides:** Edit at `/settings/matrices`; changes apply to all subsequent generations until you reset. Each generated Exercise row carries a `matrix_snapshot` so `/history` shows what was active when it was generated.
- **Logging:** `LOG_FORMAT=json` for production. Worker log lines auto-include `job_id` + `exercise_name` for grep-ability.

---

## Known gaps / pending work

- `docs/FOR_REVIEW_matrices_and_mets.md` is awaiting SME / user sign-off on the default casualty matrices, the preset bundles, and the canonical MET list.
- `BedrockCaseProvider` is a stub. Implementation deferred until GovCloud onboarding (untested provider code is worse than no provider code).
- No frontend tests (no Playwright / Vitest setup yet).
- No auth. `/settings/matrices` is currently editable by anyone with network access — fine for the current deployment, lock down when auth lands.

See [docs/DEVLOG.md](./docs/DEVLOG.md) for the full session-by-session history of what was built, why, and what was deferred.
