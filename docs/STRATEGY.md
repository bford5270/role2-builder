# Role 2 Exercise Builder — Refactor Strategy

Status: **Draft, approved direction (2026-04-28)**
Owner: TBD
Tracking: `docs/DEVLOG.md`

This document captures everything we found wrong in the current pipeline and the
agreed strategy for fixing it. It is the source of truth for the multi-session
refactor work.

---

## 1. Background

The Role 2 Exercise Builder generates a full military medical training package
(cases, MSEL schedule, WARNO, Annex Q, MEDROE, case book) from a small set of
exercise inputs. The current pipeline has three classes of problems:

- **A. Schedule correctness** — `generate_schedule` produces schedules that are
  silently truncated, wrap incorrectly across midnight, mis-assign evaluators,
  and ignore the CBRN drill window.
- **B. Casualty mix fidelity** — most exercise inputs are not actually used by
  case generation. Tactical setting, threat level, environment, region,
  footprint, METs, CBRN, detainee ops, and night ops have little or no effect on
  what cases get generated.
- **C. Throughput & reliability** — every case is its own sequential Gemini
  call inside one synchronous HTTP request, so 5–7 day exercises with 75+
  patients routinely time out and fall back to template cases that quietly
  degrade quality.

---

## 2. Problem Inventory

### A. Master Schedule Generation (`backend/main.py:254-314`)

| ID | Problem | Lines |
|----|---------|-------|
| A1 | `random.shuffle(cases)` destroys per-day case generation; cases generated for the MASCAL day get scattered across all days | 545 |
| A2 | MASCAL wave size replaces `pts_per_wave` but is not added to `total_patients`; later waves silently truncate when cases run out | 275-280 |
| A3 | Night-ops time wrap (`% 24`) doesn't shift `day_number`; 9-line offset doesn't either | 272, 293-298 |
| A4 | CBRN drill row is inserted but clinical waves still get scheduled into the same hour | 262-264 |
| A5 | Schedule list is never sorted by `(day, time)` before being written to MSEL | 478-491 |
| A6 | Route chosen by `random.choice` with no regard for triage; T1 patients can be assigned "Walk-in" with no 9-line | 289 |
| A7 | Evaluator round-robin tracks total assignments only; same evaluator can be assigned to overlapping arrivals | 234-252 |
| A8 | `assigned_counts` is initialized once outside the day loop; days don't reset evaluator rotation | 256 |
| A9 | `pts_per_wave = total_patients // num_waves` hits zero when `total_patients < num_waves`; UI doesn't warn | 267 |
| A10 | MASCAL `time_spread = 45` regardless of `mascal_patients` count (20 patients in 45 min ignores capacity) | 274 |
| A11 | Dead `if arr_min >= 60` branch (always false given the math) | 285-287 |
| A12 | CBRN time hardcoded to 0900 / 2100, even though UI exposes the toggle | 263 |
| A13 | No validation that `len(cases) == sum(day.total_patients)` before scheduling | n/a |

### B. Casualty Mix Fidelity (`backend/main.py:521-543` + supporting tables)

The whole "if/then" for case-type selection is essentially three lines:

```python
trauma_ratio = 0.85 if day.mascal or day.tactical_setting in ["Frontal Attack", "Amphibious Assault"] else 0.50
inj_types   = TRAUMA_BY_ETIOLOGY.get(day.mascal_etiology, GENERAL_TRAUMA) if day.mascal and day.mascal_etiology else GENERAL_TRAUMA
mech        = day.mascal_etiology if day.mascal else day.tactical_setting
```

Resulting blind spots:

| ID | Input | Used today? | Should drive |
|----|-------|-------------|--------------|
| B1 | `tactical_setting` | Binary (Frontal/Amphib vs other) | Per-setting trauma:DNBI ratio + characteristic etiologies |
| B2 | `threat_level` | Unused | Severity shift (T1/T2 share) and trauma:DNBI ratio |
| B3 | `environment` | DNBI only | Trauma flavor too (desert rollovers, mountain falls, arctic exposure-trauma) |
| B4 | `region` | Unused | Region-specific endemic disease patterns (CENTCOM/INDOPACOM/AFRICOM/EUCOM) |
| B5 | `night_ops` | Unused | NVG / vehicle / fall trauma bias; higher T1 share (delayed evac) |
| B6 | `cbrn` | Drill row only | Real CBRN casualties (nerve agent, blister, radiation, decon) |
| B7 | `detainee_ops` | MEDROE text only | Mixed-roster detainee patients with legal/MEDROE flags |
| B8 | `selected_footprint` | Unused | Constrain surgical case generation when no surgical team |
| B9 | `selected_mets` | Unused | Bias scenarios toward selected mission-essential tasks |
| B10 | Triage category | Gemini picks freely | Targeted distribution per day type (T1/T2/T3/T4) |
| B11 | `determine_case_phases` | Keyword matching | Fragile: penetrating TBI matches "TBI" → no DCS phase |

### C. Throughput & Output Reliability (`backend/main.py:516-575`)

| ID | Problem |
|----|---------|
| C1 | One Gemini call per casualty, sequential — 75 cases ≈ 75 calls |
| C2 | Three more Gemini calls (WARNO, Annex Q, MEDROE) on top |
| C3 | Single synchronous HTTP request; Railway / Vercel / browser timeouts kill long runs |
| C4 | No retry on individual case failure — bare `except` falls back to template |
| C5 | `create_fallback_case` silently masks failures; user gets a degraded ZIP that looks fine |
| C6 | No progress feedback beyond a static "may take 1-2 minutes" string |
| C7 | All cases generated in memory before scheduling; nothing streamed |
| C8 | Cases stored as one fat JSON column on the Exercise row |
| C9 | No idempotency / resume — if the request fails at case 60/75, all work is lost |

---

## 3. Strategic Decisions (locked in 2026-04-28)

| Area | Decision |
|------|----------|
| Casualty model | **Layered weights** — small if/then matrix per `tactical_setting`, modulated by `threat_level`, `environment`, `region`, `night_ops`, `cbrn`, `detainee_ops`, `footprint`, `selected_mets`. |
| Triage distribution | **Target distribution per day**, computed from `tactical_setting + threat_level + mascal`, then constrain each Gemini case to a chosen triage. |
| Generation strategy | **Batch + background job**. POST returns a `job_id`; worker generates in batches (~5 cases per Gemini call); frontend polls. |
| Job storage | **Postgres `exercise_jobs` table** + FastAPI `BackgroundTasks` worker. No new infrastructure (no Redis). |
| Constraints | Footprint constrains surgery; METs drive scenarios; CBRN day = real CBRN cases (~20% of trauma budget); Detainee ops = mixed roster (~10–15%). |
| Domain values | **UI-configurable matrices** for trauma ratio and triage distribution, with sensible defaults shipped server-side. |
| Frontend UX | **Stay on Tactical page, poll for progress** every 2-3s, show real progress bar with day/case status. ZIP downloads automatically when done. |
| Target scale | **Large exercises**: 5-7+ days, 75+ cases. |

---

## 4. Architecture Sketch

```
backend/
  main.py                  # HTTP layer only after refactor
  casualty_planner.py      # NEW — builds per-day plan from config (B1–B11)
  schedule_builder.py      # NEW — schedule from plan + cases (A1–A13)
  case_generator.py        # NEW — batched Gemini calls, retry, progress
  document_builder.py      # NEW — moved-out doc generation
  models.py                # NEW — SQLAlchemy: Exercise + ExerciseJob
  matrices.py              # NEW — default trauma_ratio + triage matrices

src/app/
  tactical/page.tsx        # MODIFIED — submit returns job_id, poll progress
  jobs/[id]/page.tsx       # OPTIONAL — richer job status view
  settings/matrices/page.tsx  # NEW — UI for editing matrices (Phase 6)
```

### Casualty plan shape (the contract between planner and generator)

```python
# Per day, before any LLM calls
DayPlan = {
  "day_number": int,
  "tactical_setting": str,
  "trauma_count": int,           # from layered weight matrix
  "dnbi_count": int,
  "cbrn_count": int,             # 0 unless day.cbrn
  "detainee_count": int,         # 0 unless day.detainee_ops
  "triage_targets": {"T1": int, "T2": int, "T3": int, "T4": int},
  "etiology_buckets": [          # explicit, ordered, deterministic
    {"category": "trauma", "etiology": "IED/Blast", "count": 4, "triage": "T1"},
    {"category": "dnbi",   "etiology": "Heat stroke", "count": 2, "triage": "T3"},
    {"category": "cbrn",   "etiology": "Nerve agent", "count": 1, "triage": "T1"},
    ...
  ],
  "surgical_allowed": bool,      # from footprint
  "met_emphasis": [str],         # from selected_mets
}
```

The schedule builder then operates on this plan + the generated cases keyed by
`(day_number, etiology_bucket_index)`, eliminating the global shuffle (A1) and
making MASCAL waves draw from the actual MASCAL trauma cases.

### Job lifecycle

```
POST /generate-exercise
  -> insert ExerciseJob (status=queued, total_cases=N, completed=0)
  -> schedule BackgroundTask: run_generation(job_id)
  -> return {"job_id": ..., "status": "queued", "total": N}

GET /jobs/{job_id}
  -> {"status": "running|complete|failed", "completed": k, "total": N,
      "current_phase": "cases|warno|annex_q|medroe|packaging",
      "errors": [...], "exercise_id": <set when complete>}

GET /exercises/{id}/download   # existing endpoint, used after complete
```

`run_generation` writes progress back to the row after each batch so polling is
cheap (one indexed row read).

---

## 5. Phased Implementation Plan

Each phase is independently shippable. Tests added per phase.

### Phase 0 — Foundation (this session)
- [x] Strategy + devlog docs.
- [ ] Add `pytest` config and a smoke test for `generate_exercise` end-to-end with mocked Gemini.
- [ ] Inventory current test coverage (likely none).

### Phase 1 — Casualty Planner (no LLM changes)
Goal: every input demonstrably influences the per-day plan, before we touch generation.
- [ ] Default matrices in `matrices.py` (trauma ratio, triage distribution, etiology preferences).
- [ ] `casualty_planner.build_day_plan(day, config)` returning `DayPlan`.
- [ ] Adds CBRN and detainee buckets when flags set.
- [ ] Footprint constraint: `surgical_allowed` flag respected by phase logic.
- [ ] Replace keyword-based `determine_case_phases` with phase derivation from `etiology` + `triage`.
- [ ] Unit tests covering each B-row from the inventory.

### Phase 2 — Schedule Builder Rewrite
Goal: fix every A-row.
- [ ] Move scheduling into `schedule_builder.py`, take `List[DayPlan]` + cases keyed by `(day, bucket_idx)`.
- [ ] No global shuffle (A1).
- [ ] MASCAL count flows through `total_patients` (A2).
- [ ] Cross-midnight day shift on times and 9-line (A3).
- [ ] CBRN drill window blocks clinical waves; drill time configurable (A4, A12).
- [ ] Final sort by `(day, time)` (A5).
- [ ] Route selection respects triage and route capability (A6).
- [ ] Evaluator scheduling tracks active windows (A7, A8).
- [ ] Validation step: `assert sum(plan.total_patients) == len(cases)` before scheduling (A13).
- [ ] Property-based tests (`hypothesis`) for time arithmetic.

### Phase 3 — Batched Case Generation
- [ ] `case_generator.generate_batch(plan_buckets, batch_size=5)` — single Gemini prompt returns 5 structured cases at once.
- [ ] Per-case retry with exponential backoff; failed cases logged, only fall back to template after retries exhausted.
- [ ] `generate_batch` is async; up to 3 batches in flight via `asyncio.Semaphore`.
- [ ] Surface failures in job error log instead of silently masking (C4, C5).

### Phase 4 — Background Job Infrastructure
- [ ] `ExerciseJob` SQLAlchemy model: `id, status, total_cases, completed_cases, current_phase, errors (JSON), exercise_id, created_at, updated_at`.
- [ ] `POST /generate-exercise` queues a job, returns `{job_id, total}`.
- [ ] `GET /jobs/{id}` returns progress.
- [ ] Worker uses FastAPI `BackgroundTasks`; on success links to created `Exercise` and sets status=complete.
- [ ] Idempotent resumption if worker crashes mid-run (out of scope for v1, document as known limitation).

### Phase 5 — Frontend Progress UX
- [ ] `tactical/page.tsx` submit flow: POST → poll `GET /jobs/{id}` every 2.5s → on complete, hit `GET /exercises/{id}/download`.
- [ ] Real progress bar driven by `completed_cases / total_cases` and `current_phase` label.
- [ ] Cancel button (sets job status=cancelled; worker checks status between batches).
- [ ] Error state with retry.

### Phase 6 — Matrix Configuration UI
- [ ] `/settings/matrices` page with editable trauma ratio and triage distribution tables.
- [ ] Persist per-user (or globally) in a `settings` row.
- [ ] Defaults remain in `matrices.py`; UI overrides them on a per-exercise basis.

---

## 6. Open Questions / Risks

- **Domain accuracy of default matrices.** The defaults need a real subject-matter
  review pass before exercises ship. Phase 1 lands with reasonable starting values
  but they should be flagged as draft.
- **Gemini batch fidelity.** Asking the model to return 5 well-structured cases in
  one response may degrade individual case quality vs the current 1-at-a-time
  prompt. Need to A/B compare in Phase 3 and tune `batch_size`.
- **BackgroundTasks vs a real worker.** FastAPI `BackgroundTasks` runs in the same
  process; if Railway scales horizontally a job started on instance A won't have
  its worker survive. Acceptable for v1; if we ever go multi-instance we'll need
  a queue.
- **Footprint constraint sharpness.** "No surgical team selected" → suppress
  surgical cases is clean; but should we still produce surgically-needed cases
  flagged "evac immediately, no DCS available" to train evac decision-making?
  Decision deferred to Phase 1 implementation.
- **MET coverage.** Selected METs should bias generation, but METs aren't enumerated
  anywhere in the code today; need to pin down the list.

---

## 7. Out of Scope

- Replacing Gemini with another model.
- Multi-tenant auth / login.
- Versioning of generated exercises.
- Re-running an old exercise with new logic (existing rows are frozen).
- Real-time co-editing of exercise config.
