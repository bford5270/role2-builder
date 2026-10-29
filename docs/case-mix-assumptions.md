# Case mix: how it is built, and where each number comes from

For clinician review. Code: [backend/casemix.py](../backend/casemix.py). Tests: [tests/test_casemix.py](../tests/test_casemix.py).

## How it works (bounded by the scenario, different every exercise)

1. **Envelopes.** Every tunable number is a `(min, mode, max)` range. The scenario the user selects (threat level, tactical
   settings, MASCAL etiologies, Humanitarian days, evacuation access) widens or shifts each range. The scenario therefore
   *bounds* what any exercise can look like.
2. **Draw.** At the start of each exercise one value is drawn per parameter from its envelope (triangular distribution) from a
   fresh random seed. Same settings, different draw: no two exercises are the same, and none can fall outside the envelope.
3. **Assign.** Severity is assigned to every casualty slot **first** (critical / severe / moderate / mild). The case type is then
   picked from a pool of that severity (without repeats until the pool is used up), and triage, outcome, patient population and
   night arrival follow from the drawn values.
4. **Record.** The draw (seed, envelopes, values, sources) is saved with the exercise as `config.case_mix`. The same draw reproduces
   the same exercise. The model writes each case around its assignment; the code overrides triage and disposition afterwards.

`casualty_acuity: "high"` (default `"realistic"`) is a training-emphasis switch that scales the serious-casualty share up 2 to 3 times,
still inside bounds.

## What the literature supports

| Source | What we take from it |
|---|---|
| [Kotwal et al. 2018](https://pubmed.ncbi.nlm.nih.gov/29851907/), *J Trauma Acute Care Surg* (9,557 battle-injured casualties at US Role 2 surgical teams in Afghanistan, 2008-2014) | Mortality at Role 2 by severity: **40.0% critical, 11.2% severe, 0.8% moderate, <0.1% mild**; 95.1% survived to transfer. Severity mix (my arithmetic from the abstract's percentages, approximate): **~8% critical, ~11% severe, ~24% moderate, ~55% mild**. Affiliation: US coalition 37.4%, Afghan forces 37.3%, civilian/other 21.3%, non-US coalition 4.0%. |
| [Kotwal et al. 2016](https://jamanetwork.com/journals/jamasurgery/fullarticle/2446845), *JAMA Surg* (golden-hour policy, 21,089 casualties) | Median transport fell 90 to 43 min; killed in action fell 16.0% to 9.9%. Died-of-wounds was essentially unchanged. **It does not quantify what happens when onward evacuation is denied.** |
| [Emergency War Surgery, triage chapter](https://doctorlib.org/surgery/emergency/3.html) | 10-20% of casualties reaching a surgical unit are emergent. (A secondary source cites roughly 10% immediate, 30% delayed, 50% minimal, under 10% expectant; I did not verify it against the primary text.) |
| [Frykberg 2005](https://journals.sagepub.com/doi/pdf/10.1177/145749690509400405) | 10-25% of blast casualties have life-threatening injuries. Directional only. |
| LSCO doctrine and analysis ([NDU Press](https://ndupress.ndu.edu/Media/News/News-Article-View/Article/4367958/whats-old-is-new-lsco-casualty-evacuation-in-the-21st-century/), [BMJ Mil Health](https://militaryhealth.bmj.com/node/155889)) | Evacuation to surgery took an estimated 72-84 hours in WWII island campaigns; Role 2 and prolonged-care holding is planned for up to 72 hours; timelines under contested conditions are "conditional rather than guaranteed". **Directional: no outcome numbers.** |

**Not found in the published sources I could reach:** expectant percentages, return-to-duty rates, enemy-combatant/EPW shares,
DNBI mortality, and mortality when evacuation is denied. Those parameters are bounded widely and marked **provisional** below.
Note that for the sourced parameters only the *mode* comes from the paper; the `min`/`max` are my assumed spread around it.

**Consequence worth knowing:** the old generator's cases were about 66% T1 and never produced Expectant or Died of Wounds. The
literature says most Role 2 casualties are mild or moderate, so the realistic default now produces far fewer critical cases
(roughly 10-15% T1). Use `casualty_acuity: "high"` for a training emphasis.

## Parameter registry (min / mode / max, before scenario adjustment)

| Parameter | Min | Mode | Max | Source |
|---|---|---|---|---|
| `serious_share.routine` (critical + severe, routine trauma) | 0.14 | 0.194 | 0.25 | Kotwal 2018 |
| `serious_share.mascal` | 0.2 | 0.3 | 0.45 | **provisional** |
| `serious_share.dnbi` | 0.03 | 0.08 | 0.15 | **provisional** |
| `critical_fraction` (critical of serious) | 0.3 | 0.42 | 0.55 | Kotwal 2018 |
| `moderate_of_rest` (moderate of non-serious) | 0.25 | 0.3 | 0.38 | Kotwal 2018 |
| `mortality.critical` | 0.3 | 0.4 | 0.5 | Kotwal 2018 |
| `mortality.severe` | 0.08 | 0.112 | 0.15 | Kotwal 2018 |
| `mortality.moderate` | 0.004 | 0.008 | 0.015 | Kotwal 2018 |
| `mortality.mild` | 0 | 0.0005 | 0.001 | Kotwal 2018 |
| `delay_mortality_slope` (extra mortality as evacuation access falls) | 0 | 0.9 | 1.8 | **provisional** |
| `expectant_given_critical` | 0 | 0.05 | 0.12 | **provisional** |
| `evac_base` (share evacuated when fully permissive) | 0.8 | 0.9 | 0.97 | **provisional** |
| `evac_exponent` (how steeply evacuation falls with access) | 1 | 1.5 | 2.2 | **provisional** |
| `rtd_mild` | 0.5 | 0.7 | 0.9 | **provisional** |
| `rtd_moderate` | 0.1 | 0.25 | 0.4 | **provisional** |
| `hold_hours` (time held at Role 2; doctrine plans up to 72 h) | 6 | 24 | 72 | **provisional** (min x1.5 when evacuation access is below 0.5) |
| `rtd_observation_hours` (before return to duty) | 1 | 3 | 6 | **provisional** |
| `evac_wait_hours` (times 1 minus evacuation access) | 2 | 6 | 12 | **provisional** |
| `dow_hours` (time to death; expectant casualties x1.5) | 0.5 | 2 | 6 | **provisional** |
| `civilian_share` (when authorized) | 0.12 | 0.213 | 0.3 | Kotwal 2018 |
| `partner_share` | 0.08 | 0.2 | 0.41 | **provisional** (ceiling from Kotwal 2018) |
| `enemy_share_detainee_day` (of a Detainee Ops day) | 0.06 | 0.12 | 0.2 | **provisional** |
| `enemy_share_other` | 0.04 | 0.08 | 0.12 | **provisional** |

Also provisional and fixed: severity-to-triage mapping (severe is 70% T1 / 30% T2; moderate 85% T2 / 15% T3; mild 90% T3 / 10% T2);
expectant casualties are recorded as Died of Wounds 30% of the time.

## How the scenario bounds the envelopes

| Condition | Effect |
|---|---|
| Peer/Near-Peer threat | routine serious share max x1.30; expectant-given-critical max x2.0 |
| Hybrid threat | routine serious share max x1.15; expectant-given-critical max x2.0 |
| Humanitarian or Stability day present | routine serious share x0.70-0.90; civilian share max x1.4 |
| Blast-family MASCAL (IED, VBIED, UAS, indirect fire) | MASCAL serious share max x1.20 (otherwise min x0.90) |
| `casualty_acuity: "high"` | all serious shares x2.0-3.0 |
| Evacuation access (per day, from threat level and setting) | scales the evacuated share and extra mortality; permissive 1.0-1.2, large-scale combat about 0.3 |

Evacuation access reuses the app's existing threat scale (Peer 0.33, Hybrid 0.50, Irregular 0.67, permissive 1.0) times the setting
(Retrograde 0.80, Frontal Attack and Amphibious 0.85, Defensive 0.90, Convoy 0.95, Stability 1.10, Humanitarian 1.20; Maritime x0.90),
so the case mix and the FRAGOs agree about how contested the corridor is.

## Care policy (the MEDROE and the case mix agree)

One policy is written into the MEDROE prompt **and** drives the patient mix.

- **Enemy combatants / EPW**: on when any day has Detainee Ops, or `treat_enemy_combatants: true`.
- **Host-nation civilians**: on when any day is Humanitarian Assistance or Stability Operations, or `treat_civilians: true`.
- Authorized means "some" (about 21% civilians, more on humanitarian days; about 12% of a Detainee Ops day as enemy/EPW, at least one).
- Not authorized means **one or two** across the whole exercise (an emergency-stabilization walk-in), and none in exercises under 4 patients.
- Night Ops: the same 35% share the scheduler puts in its night wave; those cases are written for night arrival and fill that wave.

## Time in Role 2 follows the outcome

The schedule used to give every casualty 45, 90 or 150 minutes in Role 2 by surgery phase alone. Now a held casualty stays for the drawn
`hold_hours` (never more than 72 h), a returned-to-duty casualty adds an observation period, a casualty awaiting evacuation waits longer the
scarcer evacuation is, and a death or expectant case takes its own time. The Role 2 census (and so the PACE saturation triggers) counts
across days, so a casualty held overnight is still there the next day.

## Found by the first real-Gemini smoke test (10 cases, 42 calls, about $0.67)

- Cases and decision trees that fall back to a template are now **marked** (`generation: "template"`, `generation_error`) and the history
  page says so, with the error type. Google's error text is never stored.
- The red-team rules assumed every casualty deteriorates when an action is missed, which forced mild casualties into templates after
  wasted review calls. For mild and moderate casualties those findings are advisory, the controller prompt asks for a proportionate layer,
  and the AI expert review is **skipped for mild casualties** (the free rules still run; `AI_REVIEW_MILD=1` reviews every case).
- Observed cost was about $0.067 per case, so the default $5 per-exercise cap covers roughly 75 cases. Larger exercises finish the remaining
  cases as templates (the job message says so). Raise `MAX_USD_PER_EXERCISE` if that is not wanted.

## Needs clinician review

- Every row marked **provisional** above, and the severity-to-triage mapping.
- The new **moderate and mild case types** (`GENERAL_TRAUMA_TIERS`, `TRAUMA_TIERS`, DNBI tiering) in `backend/main.py`.
- The surgical classification change. Added surgical terms: `penetrating`, `junctional`, `fragment wounds`, `severe burns`; exceptions that stay
  non-surgical: penetrating eye injury, hemorrhagic fever. Nine case types changed to surgical (penetrating neck trauma, junctional
  hemorrhage from fragments, severe burns with TBI or blast injury, TBI with penetrating fragment, multiple or deep fragment wounds, and others).
  An assigned mild or moderate casualty never gets a surgery phase.

## Comparison data

`docs/archive_case_mix_baseline.json` holds the rates measured from the 36 archived exercises produced by the *old* generator
(`scripts/derive_case_mix.py`). It is for comparison only and is not used at runtime.
