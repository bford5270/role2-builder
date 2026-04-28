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
