# Case-mix assumptions (for clinician review)

Each casualty's triage, outcome, patient population and night arrival are assigned **in code** from the
scenario the user selects, then handed to the case prompt as requirements ([backend/casemix.py](../backend/casemix.py)).
The model writes the case around them; the code overrides the fields afterwards so they always hold.

Every exercise draws its own mix: each baseline weight varies by a random ±15% (relative), and counts are
allocated per group so totals track the targets. Two exercises with the same settings will differ slightly.

## What is data and what is assumption

| Piece | Source |
|---|---|
| Triage mix per group (DNBI / routine trauma by tactical setting / MASCAL by etiology) | **Archive**: 36 exercises, 1,536 cases (`backend/casemix_data.json`, rebuilt by `scripts/derive_case_mix.py`) |
| Disposition mix given triage | **Archive** |
| Share of civilian and partner-force patients (12% / 14%; 28% civilian on Humanitarian and Stability days) | **Archive** |
| Surgical vs non-surgical triage multipliers (`TIER_MULT`) | **Provisional** |
| Floors for Expectant, Died of Wounds, RTD, Hold (`TRIAGE_FLOOR`, `DISPOSITION_FLOOR`) | **Provisional** |
| Evacuation-access factors and how steeply Role 3 evacuation falls (`_SETTING_ACCESS`, `ACCESS_EXPONENT = 1.5`) | **Provisional** (threat scale mirrors the app's existing `_threat_evac_mult`) |
| Enemy-combatant/EPW share (12% of a Detainee Ops day, 8% otherwise) | **Provisional** (the archive has essentially none) |

**Caveat that matters:** the archive was produced by the *old* generator, which was T1-heavy (66% T1, 94% "Evac to
Role 3") and never produced Expectant or Died of Wounds. Using it as the baseline reproduces that skew; the
conditioning (scenario, acuity, evacuation access, floors) is what changes the picture. If the baseline itself should
be more realistic, it needs target numbers from a clinician. Re-deriving from newer archives will feed the generator its own
output, so `derive_case_mix.py` takes `--max-id` to pin it to exercises made before the case mix existed.

## Evacuation access

Large-scale combat means little evacuation to Role 3; a permissive setting means a lot. Access is derived from the same
threat scale that already lengthens transit times and denies the MEDEVAC corridor in the FRAGOs:

| Threat | Access | | Tactical setting | Factor |
|---|---|---|---|---|
| Peer / Near-Peer | 0.33 | | Retrograde | 0.80 |
| Hybrid | 0.50 | | Frontal Attack, Amphibious | 0.85 |
| Irregular | 0.67 | | Defensive | 0.90 |
| HADR / Permissive | 1.00 | | Convoy | 0.95 |
| (Maritime environment ×0.90) | | | Stability / Humanitarian | 1.10 / 1.20 |

The share evacuated is scaled by `access^1.5`. What is not evacuated is held at Role 2 for prolonged care; for T1 casualties
20% of it becomes Died of Wounds. Low access also raises the Expectant floor (up to ×2). Permissive access moves
some held casualties to evacuation. Result (average of 200 simulated exercises each):

| Scenario | Evac to Role 3 | Held at Role 2 | Died of wounds |
|---|---|---|---|
| Peer threat, Frontal / Retrograde / Defensive | ~15% | ~69% | ~10% |
| Hybrid, Convoy / Defensive | ~29% | ~58% | ~7% |
| HADR/Permissive, Humanitarian / Stability | ~86% | ~10% | ~1% |

## Care policy (MEDROE and case mix agree)

One policy decides who the exercise is meant to treat; it is written into the MEDROE prompt **and** used to assign patients.

- **Enemy combatants / EPW**: on when any day has Detainee Ops (or `treat_enemy_combatants: true`).
- **Host-nation civilians**: on when any day is Humanitarian Assistance or Stability Operations (or `treat_civilians: true`).
- Authorized: "some" (about 28% civilians on Humanitarian/Stability days, 12% otherwise; about 12% enemy/EPW on Detainee Ops days, at least one per such day).
- Not authorized: only **one or two** across the whole exercise (an emergency-stabilization walk-in), none in exercises under 4 patients.
- Partner forces: always authorized, about 14%.
- Night Ops: the same 35% share the scheduler puts in its night wave; those cases are written for night arrival and fill the night wave.

## Surgical classification change (please review)

Surgery (DCS phase) was decided by a keyword list where broad non-surgical words ("TBI") won over surgical injuries.
Added surgical terms: `penetrating`, `junctional`, `fragment wounds`, `severe burns`. Named exceptions that stay non-surgical:
penetrating eye injury, hemorrhagic fever. Nine case types changed to surgical:

- Blast TBI with penetrating facial fragments
- Extremity fragment wounds with prolonged tourniquet time and wound contamination
- Junctional hemorrhage from drone-dropped munition fragments
- Multiple penetrating fragment wounds
- Multiple small deep fragment wounds to head/neck and posterior torso
- Penetrating neck trauma
- Severe burns with TBI
- Severe burns with blast injury
- TBI with penetrating fragment

## Changing it

Edit the constants at the top of `backend/casemix.py`, or rebuild the baseline with
`python scripts/derive_case_mix.py exercises.json --max-id 36`. Run `pytest tests/test_casemix.py` afterwards.
