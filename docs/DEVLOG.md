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
