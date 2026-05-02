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
pytest                        # 156 tests, ~6s
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
- `BedrockCaseProvider` is implemented (Converse API via boto3) but **untested against real AWS in this repo's CI** — has unit tests with a mocked client. First production use requires a smoke test against your account (see "Switching to Bedrock" below).
- No frontend tests (no Playwright / Vitest setup yet).

## Deploying

### Local docker run

```bash
docker build -t role2-builder .
docker run --rm -p 8000:8000 \
  -e CASE_PROVIDER=stub \
  role2-builder
```

For production-ish settings, mount a `.env` file or pass through the same env vars listed in `.env.example`.

### AWS App Runner / Fargate

The included [Dockerfile](./Dockerfile) builds a slim multi-stage image (~400MB, non-root, tini-init). App Runner can build from the source repo directly; Fargate needs a push to ECR. IAM policy templates live in [`infra/iam/`](./infra/iam/).

### Preflight before flipping providers

Before changing `CASE_PROVIDER` in production, run the doctor locally with the same env vars you plan to use:

```bash
CASE_PROVIDER=bedrock python -m backend.scripts.doctor
```

It walks every prereq (boto3 importable, AWS creds resolvable, `AWS_REGION` + `BEDROCK_MODEL_ID` set, real Converse call) and prints a green/red checklist. Exits 1 on any failure — safe to wire into a deployment script.

### Verifying Sentry

If `SENTRY_DSN` is set, exception capture is automatic — FastAPI route errors and background-job worker errors both ship to Sentry with `job_id` + `exercise_name` tags. To prove the DSN is wired up correctly:

```bash
SENTRY_DSN=https://...ingest.sentry.io/... python -m backend.scripts.sentry_test
```

Sends one info message + one test exception, both tagged `source=doctor` so you can filter them out of real noise later.

## Switching to Bedrock

The `CaseProvider` ABC is the only thing main.py talks to, so switching is an env-var change. Steps:

1. **AWS account prep**
   - Open the [Bedrock console](https://console.aws.amazon.com/bedrock/) in your target region (`us-east-1` for commercial, `us-gov-west-1` for GovCloud).
   - **Model access** → request access to the Anthropic Claude models you want. Approval is usually instant for commercial, may require justification for GovCloud.
   - Note the exact model id from the console — it varies per region. The cross-region inference profile id (prefix `us.`) is more reliable than direct model ids.

2. **IAM**
   - Grant the calling principal (your Railway service env, your laptop role, your ECS task role, etc.) `bedrock:InvokeModel` on the resolved model arn.
   - For the Anthropic Claude inference profile, the resource arn looks like:
     `arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0`
     and `arn:aws:bedrock:us-east-1:<account>:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0`.

3. **Environment variables** (see `.env.example` for the full list)
   ```
   CASE_PROVIDER=bedrock
   AWS_REGION=us-east-1
   BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
   AWS_ACCESS_KEY_ID=...      # or use instance role
   AWS_SECRET_ACCESS_KEY=...
   ```

4. **Smoke test before flipping production**
   ```bash
   # Side-by-side comparison vs Gemini, real calls to both
   python -m backend.scripts.compare_providers --providers gemini bedrock
   ```
   Outputs go to `out/compare_<timestamp>/`. The `comparison.md` table shows
   schema completeness, latency, and output verbosity per provider; raw JSON
   in `<provider>/case_*.json` lets you eyeball case quality.

5. **Flip the default**
   - Set `CASE_PROVIDER=bedrock` on the production server. No code changes required.
   - Roll back by un-setting (defaults to `gemini`) or setting back to `gemini`.

6. **GovCloud transition (later)**
   - Change `AWS_REGION=us-gov-west-1`.
   - Re-pin `BEDROCK_MODEL_ID` from the GovCloud Bedrock console (the available models / ids may differ).
   - Update the IAM grant on the GovCloud principal.
   - Zero application code changes.
- No auth. `/settings/matrices` is currently editable by anyone with network access — fine for the current deployment, lock down when auth lands.

See [docs/DEVLOG.md](./docs/DEVLOG.md) for the full session-by-session history of what was built, why, and what was deferred.
