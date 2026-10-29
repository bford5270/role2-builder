# How the schedule, the orders and the cases stay consistent

The goal: the MSEL tracks the cases, the MEDROE and Annex Q shape the care in the cases, and every document plans for the load the
schedule actually carries. The approach is to build the requirements into the prompts up front, with checks as a backstop.

## One source of numbers

`_planning_facts(config)` (backend/main.py) holds the numbers the schedule is built on: evacuation times by precedence (from the threat
level and terrain), the Role 2 holding limit (72 hours, `casemix.HOLD_LIMIT_HOURS`), and the whole-blood stock. `_facts_text` writes them as
an authoritative block that goes verbatim into the **WARNO, Annex Q and MEDROE** prompts. Before this, the MEDROE invented its own
evacuation times (routine 24 hours against Annex Q's 360 minutes) and holding limit (72 hours against 24).

The care policy (who is treated) was already shared the same way: it is written into the MEDROE and used to assign patients.

## Orders to cases

Cases are generated before the schedule, so each case prompt gets the fixed provisions that bear on it (`_orders_prompt`):

| Case | Told |
|---|---|
| held at Role 2 | the holding limit, to plan reassessments and a disposition before it |
| critical or severe | the LTOWB stock and the walking-blood-bank rule, so product choice reflects the constraint |
| expectant | the expectant policy: comfort care, reassess as resources allow |
| died of wounds | the died-of-wounds procedures |
| evacuated | the evacuation precedence times |
| enemy combatant / civilian | the detainee or civilian provisions (clinical need first, custody with the guard force, handover to host-nation care) |

Decision trees are built after the schedule, so each tree prompt also gets the **situation at arrival** (`_situation_text`): the Role 2
census against capacity, the PACE state and its driver, the whole blood on hand, and the holding limit. A tree must reflect it.

## Schedule to orders

The orders are written after the schedule, so they also receive the real load (`_schedule_facts`): casualties by outcome and severity, the
peak Role 2 census and when, how many are held and the longest hold, blood drawn and when the LTOWB stock runs out, night arrivals, the
mass-casualty surge, and the population mix.

## Schedule fixes

- Blood follows **severity** (a mild casualty never draws blood; a moderate one needs explicit bleeding) and ignores negations ("no active
  hemorrhage"). Before, a contusion drew 24 units and the stock was gone by case 8.
- A walk-in has no evacuation leg (10 minutes, not 6 hours).
- The Detainee/EPW inject is the day's first enemy-combatant case, not a separate event hours away.
- A T1 is always called in as Urgent.
- Time in Role 2 follows the outcome; the census counts across days.

## Malformed model JSON

About a quarter of case generations failed in the first live tests with `Expecting ',' delimiter` in long output and fell to templates.
`backend/jsonfix.py` repairs a missing comma and a truncated ending, a failed case is retried once, and templates are marked on the case.

## The audit

`scripts/audit_exercise.py record.json [--docs DIR]` checks a finished exercise (the JSON from `GET /exercises/{id}`, optionally with the
MEDROE/Annex Q/WARNO text extracted into `DIR`): completeness, chronology, night windows, triage/disposition/surgery agreement between rows
and cases, time in Role 2 by outcome, blood, FRAGOs in force, the CBRN drill and detainee inject, the census, and, with the documents, whether the
MEDROE states the care policy, whether the MEDROE and Annex Q agree on evacuation times and holding limit, and whether the cases cite the
orders. A generated-schedule version runs in `tests/test_orders_schedule.py`.
