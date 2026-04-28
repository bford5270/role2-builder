# Role 2 Exercise Builder — Devlog

Running log of refactor sessions. Newest entry on top. Each entry should answer:
**what state did I find, what did I do, what's next.**

Companion to `docs/STRATEGY.md`. Don't duplicate the strategy here — link to it.

Format:
```
## YYYY-MM-DD — short title
**Branch:** ...
**Phase:** Phase N — name (see STRATEGY.md §5)
**Status going in:** ...
**Done this session:** ...
**Next:** ...
**Open questions / blockers:** ...
```

---

## 2026-04-29 (continued) — Phase 6b complete: matrix configuration UI

**Branch:** `claude/review-schedule-issues-pjHcI`
**Phase:** Phase 6b — Matrix Configuration (frontend)
**Status going in:** Phase 6a committed (c8c9e9e), 111 tests green. Backend can read/write/reset matrix overrides and apply presets, but there's no UI for it.

**Done this session:**
- New `src/app/settings/matrices/page.tsx`:
  - Loads `GET /settings/matrices` and `GET /settings/matrices/presets` on mount.
  - Maintains an editable `draft` MatrixView; cells with values that differ from defaults highlight in amber.
  - Section components:
    - `SectionTraumaRatio`: per-tactical-setting numeric editor (0–1).
    - `SectionTriageDist`: T1/T2/T3/T4 table per setting with a live row sum that turns red when ≠ 1.0.
    - `SectionMascalDist`: same shape for the MASCAL override row.
    - `SectionThreatShift`: deltas per Low/Medium/High (trauma_ratio, t1_pp..t4_pp).
    - `SectionStringLists`: tag-style add/remove editor used three times (etiology_by_setting, dnbi_by_region, cbrn_etiologies).
  - **Diff-and-PUT save semantics**: `onSave` compares the draft to the loaded defaults and only sends changed fields as overrides. Saving with no diffs is a no-op + status message.
  - Preset selector dropdown applies via `POST /settings/matrices/presets/{name}/apply`.
  - "Reset to defaults" button calls `DELETE /settings/matrices`.
  - Status / error banners.
- `src/app/page.tsx`: added a "Matrix Configuration →" link alongside the existing "View Past Exercises →" link in the home-page footer.
- `tsc --noEmit` is clean. Couldn't run `next build` end-to-end (sandbox blocks Google Fonts) — same constraint as Phase 5.

**Frontend design notes:**
- The page deliberately edits the merged view (not the sparse overrides) because that's what instructors think in. The diff-on-save pattern means we don't echo defaults back to the server, so a partial preset stays partial after a manual edit-and-save round trip.
- "Default" highlighting (amber border on changed cells) gives a quick visual diff against the factory baseline — useful when a preset is loaded.

**Phase 6 inventory check:**
- ✅ Headlines + list editors all editable.
- ✅ Single global override + per-exercise snapshot (snapshot saved in Phase 6a).
- ✅ Open access for now (no auth — gap documented).
- ✅ Reset + named presets (3 shipped: usmc_default, permissive_humanitarian, high_intensity_contingency).

**Next (carry-forwards from earlier devlog entries):**
- SME review of the draft matrices in `matrices.py` AND the preset bundles before any of this is held out as authoritative.
- Canonical MET list — the `MET_BIAS` table is still illustrative.
- Bedrock model id + region pinning at GovCloud onboarding (the `BedrockCaseProvider` stub is ready).
- Phase 7 (tablet runner) remains future work — schema-ready (stable IDs landed in Phase 1, matrix snapshot landed in Phase 6a).

**Open questions / blockers:**
- No new ones from Phase 6b.

---

## 2026-04-29 (continued) — Phase 6a complete: matrix override backend + presets

**Branch:** `claude/review-schedule-issues-pjHcI`
**Phase:** Phase 6a — Matrix Configuration (backend)
**Status going in:** Phase 5 committed (e3c1090), 90 tests green. The casualty / triage matrices in `matrices.py` are immutable module constants; instructors can't tune them without a code change.

**Decisions confirmed before coding:**
- Scope: headlines + list editors (trauma_ratio_by_setting, threat_level_shift, base_triage_distribution, mascal_triage_distribution, etiology_by_setting, dnbi_by_region, cbrn_etiologies). Defer the long DNBI_BY_ENVIRONMENT and TRAUMA_BY_ETIOLOGY tables.
- Persistence: single global override + per-exercise snapshot. Each Exercise row carries the `MatrixView` it was generated against.
- Auth: open access for now. Documented as a known gap.
- Presets: reset button + named preset bundles shipped server-side (3 to start).

**Done this session:**
- `backend/matrix_store.py` (new):
  - `MatrixOverrides` Pydantic model with optional fields per editable table; per-field validators (triage distributions sum to 1, ratios in [0,1], threat-level shift keys constrained, etc.).
  - `MatrixView` — the merged view (defaults + overrides) the planner reads. `MatrixView.defaults()` snapshots `matrices.py`; `MatrixView.from_overrides(o)` produces the merged result.
  - `MatrixStore` ABC + `InMemoryMatrixStore` (asyncio.Lock + model copies) + `PostgresMatrixStore` (single-row id=1, short-lived sessions via `asyncio.to_thread`).
  - `get_matrix_store()` factory; `get_active_view()` helper for the pipeline; `reset_matrix_store_for_tests()`.
- `backend/db.py`: added `MatrixSetting` SQLAlchemy model (singleton row) and `Exercise.matrix_snapshot` JSON column.
- `backend/casualty_planner.py`: refactored `trauma_ratio`, `triage_distribution`, `_weighted_etiology_pool`, and `build_day_plan` to accept an optional `view: MatrixView`. Default falls back to module constants — every existing test continues to pass without modification. `dnbi_by_region` and `cbrn_etiologies` now read from the view too.
- `backend/main.py`:
  - `_run_exercise_pipeline` now reads the active view once and forwards to the planner.
  - Pipeline returns `matrix_snapshot` in artifacts; `_save_exercise_to_db` persists it onto the Exercise row.
  - New endpoints:
    - `GET /settings/matrices` — overrides + merged view + defaults.
    - `PUT /settings/matrices` — Pydantic-validated overrides write.
    - `DELETE /settings/matrices` — clears overrides; planner reverts to defaults.
    - `GET /settings/matrices/presets` — list shipped bundles.
    - `POST /settings/matrices/presets/{name}/apply` — load preset into overrides.
- `backend/presets.py` + `backend/preset_data/*.json` (new):
  - `usmc_default.json` — empty overrides (explicit anchor).
  - `permissive_humanitarian.json` — DNBI-skewed for HA/DR.
  - `high_intensity_contingency.json` — near-peer combat with critical triage skew. All flagged DRAFT pending SME review.
- `backend/tests/test_matrix_store.py` (new): 17 tests covering validation rejection, merge behavior, in-memory CRUD, planner reading overrides, and the settings endpoints (including preset application).
- 111 tests passing total in ~1.5s.

**Key design note:** the planner's existing tests didn't change. The optional `view` parameter defaults to `MatrixView.defaults()` which snapshots `matrices.py`, so legacy callers and tests behave identically.

**Next (Phase 6b — Frontend matrix editor):**
- `/settings/matrices` Next.js page with sections for each matrix.
- Numeric editors with live "must sum to 1" validation for triage distributions; range checks for ratios.
- List editors for etiology_by_setting / dnbi_by_region / cbrn_etiologies (add/remove rows).
- Preset selector dropdown + Apply button.
- Reset to defaults button.
- Save button — diffs the form vs the loaded view, sends only changed fields as overrides.

**Open questions / blockers:**
- All draft preset values (especially high_intensity_contingency) need SME review before they ship as anything other than illustrative.
- Pydantic / SQLAlchemy deprecation warnings still cosmetic.

---

## 2026-04-29 (continued) — Phase 5 complete: frontend polling UX + graceful cancel

**Branch:** `claude/review-schedule-issues-pjHcI`
**Phase:** Phase 5 — Frontend Progress UX (+ graceful cancel mechanism)
**Status going in:** Phase 4 committed (805d075), 81 tests green. Job-mode endpoints exist on the backend, but `tactical/page.tsx` still POSTs to legacy `/generate-exercise` and shows a static "may take 1-2 minutes" string.

**Decisions confirmed before coding:**
- Cancel semantics: graceful between batches (worker checks status between batches; in-flight LLM call finishes; clean exit). No hard-stop.

**Done this session:**

*Backend cancel mechanism:*
- `JobStatus.cancelled` enum value + `CANCELLABLE_STATUSES = {queued, running}` constant.
- `JobStore.mark_cancelled` and `JobStore.request_cancel` on both `InMemoryJobStore` and `PostgresJobStore`. `request_cancel` returns False if the job is already complete/failed (no-op) or unknown.
- `case_generator.generate_all_cases`: new `is_cancelled: Callable[[], Awaitable[bool]]` parameter. Each batch coroutine checks before queuing for the semaphore and again after acquiring it; in-flight batches finish (no orphaned LLM calls). `GenerationResult.cancelled` flag bubbles up.
- `_run_exercise_pipeline`: threads `is_cancelled` through to the case generator, also checks between phases. Returns `{cancelled: True}` on cancel; partial work is discarded (no half-saved Exercise rows).
- `_run_exercise_job_worker`: binds an `is_cancelled` closure that polls the store; honors a pre-running cancel (won't even start the LLM); preserves `current_phase='cancelled'` against stale phase updates.
- `POST /jobs/{id}/cancel`: 404 if unknown, 409 if already terminal, 200 + `{accepted, status, current_phase}` on success.

*Frontend (`src/app/tactical/page.tsx`):*
- POST flow now hits `POST /jobs/generate-exercise` and stores `{job_id, total_cases}`.
- `pollJob()` polls `GET /jobs/{job_id}` every 2.5s; on `complete` fetches `GET /jobs/{job_id}/download` and triggers the browser download; on `failed` shows `error_message`; on `cancelled` shows a clean cancelled state.
- Real progress bar driven by `progress` (0–1) plus a `current_phase` label table (`PHASE_LABELS`) covering queued / planning / generating_cases / generating_docs / packaging / complete / failed / cancelled.
- Cancel button visible while `status` is queued/running; calls `POST /jobs/{job_id}/cancel`; tolerates 409 (job already done — race).
- Warning banner when `errors_count > 0` so degraded packages no longer look like clean ones; pointer to `generation_summary.json` inside the ZIP.
- `useEffect` cleanup clears the polling timer on unmount.

*Tests (90 passing total in ~1.5s):*
- `test_jobs.py`: `request_cancel` lifecycle on InMemoryJobStore (queued, running, complete-noop, unknown). HTTP cancel endpoint races against the fast stub provider, so the test accepts either 200 or 409 — both are correct outcomes.
- `test_case_generator.py`: new `_SlowProvider` introduces an async sleep so cancel timing is deterministic. Asserts `result.cancelled=True`, `total_returned > 0`, `total_returned < total_requested`. Companion test verifies `is_cancelled=lambda: False` produces full completion.

**Couldn't verify in sandbox:** Next.js production build fails to fetch Google Fonts (no outbound network), so I ran `tsc --noEmit` instead — clean. The frontend will need a manual UX walkthrough on a real browser before declaring Phase 5 done end-to-end.

**Open questions / blockers:**
- Pydantic v2 + SQLAlchemy 2.0 deprecation warnings still cosmetic.
- Phase 6 (matrix configuration UI) and the carry-forwards (SME matrix review, canonical METs, Bedrock onboarding) remain.

**Next (Phase 6 — Matrix Configuration UI):**
- New `/settings/matrices` page with editable trauma-ratio + triage-distribution tables, plus environment/region/etiology pools.
- Persist overrides in a new `settings` row (or a single global JSON blob).
- Defaults stay in `matrices.py`; the planner reads UI overrides if present.

---

## 2026-04-29 (continued) — Phase 4 complete: background job infrastructure

**Branch:** `claude/review-schedule-issues-pjHcI`
**Phase:** Phase 4 — Background Job Infrastructure
**Status going in:** Phase 3 committed (d3ca994), 69 tests green. Sync `/generate-exercise` runs the whole pipeline in one HTTP request — fine for small exercises but hits Railway / browser timeouts at the 5-7 day / 75+ case scale we're targeting.

**Decisions confirmed before coding:**
- Add new `POST /jobs/generate-exercise` alongside the legacy sync endpoint (no breaking change).
- Two-table model: separate `exercise_jobs` row tracks status/progress/errors; existing `exercises` row holds the finished package and is created on completion.
- DB stays optional — `InMemoryJobStore` falls back when `DATABASE_URL` is unset, same contract as the rest of the app.
- Global `asyncio.Semaphore(1)` serializes job execution; additional submissions queue with status='queued'.

**Pre-Phase-4 cleanup (folded in):**
- Dropped dead `generate_case_sync`, `determine_case_phases`, `CASE_SYSTEM_PROMPT`, and the local copies of `DNBI_BY_ENVIRONMENT` / `TRAUMA_BY_ETIOLOGY` / `GENERAL_TRAUMA` from `main.py` (single source of truth in `matrices.py` / `prompts.py`).
- Routed `generate_warno`, `generate_annex_q`, `generate_medroe`, and `/generate-name` through `provider.generate_text()`. Removed the direct `genai.Client` import from `main.py`. **Now every model call from `main.py` flows through `CaseProvider`.** The GovCloud transition only requires implementing `BedrockCaseProvider`.

**Done this session:**
- `backend/db.py` (new): `Base`, `Exercise`, new `ExerciseJob` SQLAlchemy model (status, current_phase, total_cases, completed_cases, errors JSON, exercise_id FK, error_message, generation_summary, timestamps), engine/SessionLocal lifecycle, `init_db()`. Pulled out so `jobs.py` can import without circular dependency.
- `backend/jobs.py` (new):
  - `JobRecord` Pydantic model with computed `progress` property.
  - `JobStore` ABC with `create / get / update_progress / append_errors / mark_running / mark_complete / mark_failed / list_recent`.
  - `InMemoryJobStore` — dict-backed, asyncio.Lock-protected, returns model copies (not references) so the lock is the only shared state.
  - `PostgresJobStore` — short-lived sessions per call via `asyncio.to_thread` so we never hold a transaction across batch cycles.
  - `get_job_store()` factory: Postgres when `SessionLocal` is set, in-memory otherwise.
  - `get_job_semaphore()` lazily-created `asyncio.Semaphore(1)` (avoids capturing the wrong event loop at import time).
  - `reset_singletons_for_tests()` test hook.
- `main.py` refactor:
  - Extracted `_run_exercise_pipeline(config, on_case_progress, on_phase) -> artifacts` from the legacy endpoint body. Sync `/generate-exercise` now calls into it.
  - `_save_exercise_to_db()` and `_build_zip()` helpers shared between sync and async paths.
  - `_run_exercise_job_worker(job_id)` — async worker that acquires the global semaphore, marks the job running, drives the pipeline, hooks `on_case_progress` (sync) → `asyncio.run_coroutine_threadsafe` → store update, persists the Exercise row, marks the job complete with the generation_summary.
  - New endpoints:
    - `POST /jobs/generate-exercise` — queues via `BackgroundTasks`, returns `{job_id, total_cases, status, current_phase, created_at}`.
    - `GET /jobs/{job_id}` — current state including `progress` (0–1) and `errors_count`.
    - `GET /jobs` — recent jobs list.
    - `GET /jobs/{job_id}/download` — 409 until complete, 404 if no Exercise persisted, otherwise delegates to `download_exercise(exercise_id)`.
- `backend/tests/test_jobs.py` (new): 12 tests covering JobStore CRUD/state transitions and end-to-end lifecycle through FastAPI's TestClient with the stub provider.
- `requirements-dev.txt`: added `httpx==0.27.2` for the TestClient.
- 81 tests passing total in ~1.7s.

**Hot-path note:** TestClient runs BackgroundTasks on the event loop after the response returns, so the test polls `/jobs/{id}` until `status` leaves `running` — same pattern the frontend will use in Phase 5.

**Next (Phase 5 — Frontend Progress UX):**
- Update `src/app/tactical/page.tsx` to:
  - POST `/jobs/generate-exercise`, get `job_id`.
  - Poll `GET /jobs/{job_id}` every 2.5s, show real progress bar driven by `completed_cases / total_cases` and `current_phase`.
  - On `complete`, hit `GET /jobs/{job_id}/download` for the ZIP.
  - Surface `errors_count` and `generation_summary` to the user (so degraded packages no longer look like clean ones).
  - Cancel button — sets a `cancelled` status the worker can check between batches (also touches `case_generator.on_progress`).

**Open questions / blockers:**
- SQLAlchemy 2.0 deprecation warning on `declarative_base()` — should switch to `sqlalchemy.orm.declarative_base()` at some point. Cosmetic for now.
- Pydantic v2 deprecation warning on `.dict()` — switch to `.model_dump()`. Cosmetic.
- Phase 5 cancel-button semantics: cancel between batches (graceful, ~5s lag) vs hard-stop. Bring up before implementation.
- Same as before: SME matrix review, canonical MET list, Bedrock model id pinning at GovCloud onboarding.

---

## 2026-04-29 (continued) — Phase 3 complete: batched case generation

**Branch:** `claude/review-schedule-issues-pjHcI`
**Phase:** Phase 3 — Batched Case Generation
**Status going in:** Phase 2 committed (cc59248) with 61 tests green. Schedule was correct but case generation was still 1 sequential Gemini call per case inside one HTTP request.

**Open questions answered (defaults, noted for confirmation):**
- *Sync ZIP vs job-mode*: keeping the sync `/generate-exercise` endpoint for Phase 3; `/jobs` lands in Phase 4. Smaller blast radius, sticks to STRATEGY.md plan.
- *Footprint suppression*: existing planner-side category demotion (trauma_surgical → trauma_non_surgical when no surgical capability) is sufficient; the prompt-level "evac required, no DCS available" refinement is deferred — not blocking.

**Done this session:**
- `backend/providers/base.py`: added `BatchItem` dataclass and async `generate_batch()` on the `CaseProvider` ABC. Default impl fans out single calls via `asyncio.gather` so every provider gets batching for free; concrete providers can override for one-prompt-N-cases.
- `backend/prompts.py`: added `case_batch_prompt(items)` that asks the model to return `{"cases": [...]}` with one numbered block per item.
- `backend/providers/gemini.py`: overrode `generate_batch()` — single Gemini call returning a JSON array of N cases, parsed and stamped with stable IDs.
- `backend/case_generator.py` (new): orchestrator with:
  - Item materialization from `(plan, bucket, count)` keyed on `(day_number, bucket_pos, p_idx)`.
  - Batches don't cross day boundaries — keeps progress reporting honest and contains blast radius.
  - `asyncio.Semaphore(concurrency)` bounds in-flight batches (default 3).
  - `_run_batch_with_retry()`: retries the batch path up to N times with exponential backoff, then falls through to per-item single calls (also with retry), then to the caller-provided `fallback_factory`.
  - Structured `GenerationError` records every failure that hit the fallback path.
  - `GenerationResult` carries `total_requested`, `total_returned`, `total_fallback`, and the error list.
- `main.generate_exercise` rewired:
  - Replaces sequential per-bucket loop with `await generate_all_cases(plans, provider, ...)`.
  - `CASE_BATCH_SIZE` (default 5) and `CASE_BATCH_CONCURRENCY` (default 3) env vars.
  - Embeds `<exercise>_generation_summary.json` in the ZIP so a half-degraded package no longer looks like success.
  - Adds response headers `X-Generation-Total / Returned / Fallback / Errors` for the frontend to surface a warning.
- `backend/tests/test_case_generator.py` (new): 8 tests covering happy path, progress callback, batch retry → single-call fall-through, total-failure → fallback factory, no-fallback → missing cases (so A13 in the schedule builder catches it), and direct `_run_batch_with_retry` cases.
- 69 tests passing total in ~0.6s (added `initial_backoff=0.0` knob so retry tests run instantly).

**Hot path improvement for the GovCloud transition:** every model call from `main` now goes through `provider.generate_batch` or `provider.generate_case`. To run in GovCloud, only `BedrockCaseProvider` needs to be implemented — main.py and case_generator.py don't change.

**Next (Phase 4 — Background Job Infrastructure):**
- New SQLAlchemy `ExerciseJob` model (`status`, `total_cases`, `completed_cases`, `current_phase`, `errors` JSON, `exercise_id`, timestamps).
- `POST /generate-exercise` returns `{job_id, total}` immediately and queues the work via `BackgroundTasks`.
- `GET /jobs/{id}` returns current progress.
- Worker hooks `on_progress` to UPDATE the job row each batch.
- Frontend (Phase 5) polls `/jobs/{id}` for the real progress bar.

**Open questions / blockers:**
- Confirm Phase 3 defaults (sync ZIP, deferred evac-flag prompt) are fine; otherwise revisit before Phase 4.
- Same as before: SME review of matrices, canonical MET list, Bedrock model id pinning at GovCloud onboarding.

---

## 2026-04-29 (continued) — Phase 2 complete: schedule rewrite
**Branch:** `claude/review-schedule-issues-pjHcI`
**Phase:** Phase 2 — Schedule Builder Rewrite
**Status going in:** Phase 1 committed (8f3cf9b) with 43 tests green. `generate_schedule` and `assign_evaluator` in `main.py` still had bugs A1–A13 from STRATEGY.md §2.

**Done this session:**
- Extended `DayPlan` to forward operational flags (`night_ops`, `mascal`, `mascal_patients`, `mascal_etiology`, `cbrn`, `detainee_ops`, `total_waves`) so the schedule builder doesn't need a separate DayConfig channel.
- New `backend/schedule_builder.py`:
  - Minute-based time arithmetic with `(start_hour, total_minutes)` shift model; cross-midnight handled by absolute-minute conversion (`minutes_to_hhmm` returns a `crosses_midnight` flag) — fixes A3 / A11.
  - `ScheduleEvent` dataclass with `to_dict()` matching the existing MSEL columns plus `case_id` back-reference for the assessment vehicle.
  - Per-day case validation (A13).
  - Wave assignment: MASCAL day puts mascal patients in wave 0 *additively*, remaining patients spread across other waves (A2).
  - `_split_into_waves` handles the small-totals edge (A9); MASCAL spread scales with patient count (A10).
  - `choose_route` keyed on triage + category + mascal-context (A6).
  - `_EvalState` tracks busy windows per (specialty, slot); idle-first across the priority list, fall through on overload (A7, A8).
  - CBRN drill window blocks clinical waves; arrivals that land in the drill window are pushed to drill_end + stagger; drill time configurable per-day (A4, A12).
  - Final `events.sort(key=_sort_key)` on `(day, minutes_from_shift_start)` (A5).
- `main.py` wired through: `generate_exercise` now builds `DayPlan`s from inputs, generates cases per bucket (still sequentially via Gemini for now — Phase 3 will batch), and calls `build_schedule(plans, cases_by_day, specialists)`. Removed old `generate_schedule` / `assign_evaluator` / `determine_case_phases`. Added `_bucket_to_case_inputs` to translate planner buckets into `(case_type, mechanism)` for the LLM.
- `backend/tests/test_schedule_builder.py` — 16 tests covering each A-row plus hypothesis property tests for time arithmetic.
- `backend/tests/test_pipeline_integration.py` — 2 end-to-end tests running the full planner → StubCaseProvider → build_schedule flow with a 2-day exercise (one quiet, one MASCAL+CBRN+night).
- 61 tests passing total. No regressions in Phase 1 tests.

**Bug found and fixed mid-session:** `_EvalState.assign` returned the busiest slot of the top-priority specialty instead of falling through to the next specialty when all top-priority slots were busy. Now does idle-first across the whole priority list (Pass 1), only falls back to least-busy across all priorities when the system is fully booked (Pass 2).

**Next (Phase 3 — Batched Case Generation):**
- Add `CaseProvider.generate_batch(buckets, batch_size=5)` returning N cases per Gemini call.
- Async fan-out via `asyncio.Semaphore` (max 3 batches in flight).
- Per-case retry with exponential backoff; failures surface in a structured error log instead of silently falling back.
- Switch `main.generate_exercise` to use the provider + batch path. (This is the key step for the GovCloud transition: only the provider implementation has to change.)
- Decide footprint-suppression policy (hard suppress vs evac-flag) before wiring the prompt for surgical cases.

**Open questions / blockers:**
- Same as before: SME review of matrices, canonical MET list, Bedrock model id pinning at GovCloud onboarding.
- Phase 3 needs a concrete answer on whether `generate_exercise` should keep returning a sync ZIP (legacy) while we add a parallel `POST /jobs` path (Phase 4), or whether Phase 3 should immediately move to job-mode.

---

## 2026-04-29 — Phase 1 kickoff: north star, planner, provider, stable IDs
**Branch:** `claude/review-schedule-issues-pjHcI`
**Phase:** Phase 1 — Casualty Planner + Provider Abstraction + Stable IDs
**Status going in:** Strategy doc and devlog committed yesterday. Codebase unchanged. User added new strategic context: long-term home is AWS GovCloud, co-hosted with the R2 Assessment Vehicle, running on a tablet that drives simulation, case content, assessment, and scheduling from a single environment.

**Done this session:**
- Added §1.5 "North Star" to STRATEGY.md capturing the GovCloud + tablet + assessment-vehicle vision and its concrete implications for today's work.
- Locked in (with the user):
  - `CaseProvider` interface from day 1; Gemini today, Bedrock-Claude later.
  - Builder now, runner later — schema designed for both.
  - Stable IDs (UUIDs) added everywhere in the case schema now.
  - Builder online, runner offline-capable later.
- Updated Phase 1 plan in STRATEGY.md §5 to include provider abstraction and stable IDs (no longer "no LLM changes" — it now refactors the LLM call site behind an interface).
- Added Phase 7 placeholder for the tablet runner (future, out of scope).

**Done (this session, continued):**
- `requirements-dev.txt` (pytest, pytest-asyncio, hypothesis), `backend/pytest.ini`, `backend/tests/{__init__,conftest}.py`, `.gitignore` python entries, `backend/__init__.py`.
- `backend/matrices.py` — full default tables: trauma ratio per setting, threat-level shifts, base + MASCAL triage distributions, night-ops shift, etiology pools per setting, environment trauma flavor, DNBI by environment AND region, CBRN etiologies, detainee case types, footprint-keyword detection, MET bias, phase derivation per category.
- `backend/casualty_planner.py` — pure-logic `build_day_plan()` returning a `DayPlan` of `EtiologyBucket`s. Deterministic with optional seed. Largest-remainder integer rounding. Self-consistent triage_targets computed from actual buckets.
- `backend/prompts.py` — extracted `CASE_SYSTEM_PROMPT` plus a provider-agnostic `case_user_prompt()` that can target a specific triage.
- `backend/providers/{__init__,base,gemini,bedrock,stub}.py` — `CaseProvider` ABC, factory by `CASE_PROVIDER` env var, server-side `inject_stable_ids()` stamping UUIDs on case_id / phase_id / action_id / vitals_id / contingency_id. Bedrock is a stub raising `NotImplementedError` for now; will be filled in at GovCloud onboarding.
- `main.py` updated to call `inject_stable_ids` on both Gemini-generated and fallback cases.
- 43 unit tests across `test_matrices.py`, `test_casualty_planner.py`, `test_providers.py`. All passing. Each B-row from STRATEGY.md §2 has a corresponding behavioral test.

**Bug found and fixed mid-session:** `_largest_remainder` was being called with a distribution that didn't sum to 1 (trauma share scaled the dist values), leaving up to 3 patients unallocated. Reworked to give each category its own normalized distribution and `total`, then derive day-level `triage_targets` from the actual buckets.

**Next (Phase 2 — Schedule Builder Rewrite):**
- Move scheduling out of `main.py` into `backend/schedule_builder.py`, take `List[DayPlan]` + cases keyed by `(day, bucket_idx)`.
- Eliminate global `random.shuffle(cases)` (A1).
- Fix MASCAL wave truncation (A2), cross-midnight wrap (A3), CBRN-window collision (A4), missing time sort (A5), route-vs-triage mismatch (A6), per-day evaluator state (A7, A8), zero-pts-per-wave edge (A9).
- Property-based tests with hypothesis for time arithmetic.

**Open questions / blockers:**
- Default matrix values flagged as DRAFT — need SME review before shipping (CENTCOM/INDOPACOM DNBI, threat-level shifts, MASCAL triage skew).
- Canonical MET list still needed; `MET_BIAS` table currently illustrative.
- Bedrock model id and region pinned at GovCloud onboarding, not now.
- Footprint surgical-suppression: today we downgrade trauma_surgical → trauma_non_surgical. Should it also tag the case "evac required, no DCS available" for the case generator? Decide before Phase 3.

---

## 2026-04-28 — Strategy lock-in
**Branch:** `claude/review-schedule-issues-pjHcI`
**Phase:** Phase 0 — Foundation
**Status going in:** No prior refactor work; bugs and missing-input behavior identified across `generate_schedule` and `generate_exercise`. Output struggles for large exercises (>50 cases) due to sequential per-case Gemini calls inside one HTTP request.

**Done this session:**
- Reviewed `backend/main.py` end-to-end; catalogued 13 schedule bugs (A1–A13), 11 casualty-mix gaps (B1–B11), and 9 throughput problems (C1–C9). All in `docs/STRATEGY.md` §2.
- Locked in strategic decisions with the user (`docs/STRATEGY.md` §3):
  - Layered weights for casualty mix.
  - Per-day target triage distribution, constrained at generation time.
  - Batch + background job, Postgres `exercise_jobs` table, FastAPI BackgroundTasks.
  - Footprint constrains surgery; METs drive scenarios; CBRN day produces real CBRN casualties; detainee_ops produces detainee patients.
  - UI-configurable matrices with server-side defaults.
  - Frontend stays on Tactical page and polls.
  - Target scale: 5–7+ days, 75+ cases.
- Drafted phased plan (`docs/STRATEGY.md` §5) — six phases, each independently shippable.
- Created this devlog.

**Next (Phase 0 wrap, then Phase 1):**
- Add `pytest` config and a smoke test for `generate_exercise` with mocked Gemini.
- Begin Phase 1 — implement `casualty_planner.py` and default `matrices.py`.
- Decide concrete starting values for the trauma-ratio and triage-distribution matrices (draft, flagged for SME review).

**Open questions / blockers:**
- Need the canonical list of METs that the UI offers, to map them to scenario biases (Phase 1).
- Need SME review of default matrices before they ship to users.
- Footprint constraint sharpness: hard suppress vs flag-for-evac — defer to Phase 1 implementation.

---
