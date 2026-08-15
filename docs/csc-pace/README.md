# Crisis Standards of Care: A PACE Framework (Role 1–2 Continuum)

> Integrating JTS CPG tiered recommendations with operational planning for the Role 1–2
> continuum. Compiled for CDR Brian S. Ford, MC, USN — Chief Medical Officer, 1st Medical
> Battalion, 1st MLG. Framework co-authors: CDR Brian S. Ford, MC, USN · Dan Hanfling, MD ·
> John L. Hick, MD.

This folder holds the source Crisis Standards of Care (CSC) PACE materials and this
markdown summary. It is the reference the Role 2 Exercise Builder uses to recommend a Role 2
**PACE state** from the exercise's own computed strain signals (blood, saturation, MASCAL,
evacuation posture).

## Bottom line

The USMC lacks a shared mental model for **planned degradation** of medical care standards
during contested operations. JTS CPGs already tier recommendations as *Preferred / Acceptable
/ Emergency* (a.k.a. *best / better / minimum*). The PACE construct links those clinical tiers
to **operational triggers** — Class VIII / evacuation / MASCAL state — so every transition is
**planned, briefed, and recognized, not improvised**. Each transition also communicates to
higher exactly which finite resources restore capability at each level.

## Key assumptions

1. Contested logistics with degraded or interdicted resupply is the **expected** operating environment.
2. Evacuation timelines will not reliably meet doctrinal standards; prolonged casualty care is likely.
3. JTS CPGs remain the clinical reference at all PACE levels — as executable guidance or recovery targets.
4. Providers and commanders are pre-briefed on the framework and transition authorities during workup.
5. CO/CMO pre-authorize transition decisions; **moral burden is institutional, not individual.**

## The four PACE states

| PACE level | JTS CPG tier | Clinical posture | Transition triggers | Ethical frame | COP status |
|---|---|---|---|---|---|
| **PRIMARY** | Preferred — full CPG compliance (Best) | Full Role 2: component blood therapy, dual surgical teams, complete AMAL, monitoring per CPG; evac timelines met. | **Log:** Class VIII resupply < 24 h; blood per MTP. **Evac:** CASEVAC/MEDEVAC within doctrinal timelines. | Prudence | Green |
| **ALTERNATE** | Acceptable — known substitutions within CPG (Better) | Degraded but capability present. Shortfalls from supply/personnel; CPG-acceptable substitutions activated (e.g., LTOWB for components). | **Log:** Resupply 24–72 h; consumption outpacing replenishment. **Evac:** delays present but functional. **Staff:** key billets gapped but mitigated. | Prudence + Justice | Yellow |
| **CONTINGENCY** | Minimum standard in JTS CPG | Capability gaps present; **reverse triage** activated; allocation framework engaged. | **Log:** Resupply > 72 h or interdicted; critical AMAL shortfalls. **Evac:** non-functional or severely delayed. **MASCAL:** patient load exceeds throughput. | Justice + Courage | Red |
| **EMERGENCY** | Below minimum (cannot afford minimum guideline-adherent care) | Survivability focus; unit conservation; pre-briefed boundaries in effect. | **Log:** supply chain severed; residual Class VIII only. **Evac:** no movement possible. **Comms:** degraded or lost; operating independently. | Courage + Temperance | Black |

## Degradation & recovery triggers (bidirectional, pre-briefed)

| Transition | Degradation trigger | Recovery trigger (reverse) |
|---|---|---|
| PRIMARY ⇄ ALTERNATE | Resupply > 24 h **OR** evac slipping doctrinal → substitutions begin | Resupply < 24 h restored → return to standard CPG compliance |
| ALTERNATE ⇄ CONTINGENCY | Resupply > 72 h **OR** MASCAL > throughput → CO/CMO activates allocation authority | Resupply < 72 h sustained **AND** throughput restored → gaps closing |
| CONTINGENCY ⇄ EMERGENCY | Supply severed **OR** comms lost → CO/CMO pre-brief in effect | Resupply or comms restored → partial capability |

## Synchronized mental model (swimlane)

Each PACE state defines one operational reality that **command, provider, logistics, and higher
echelon** all see at once — removing the legitimacy gap between "what the provider is doing" and
"what the commander has authorized."

| Actor | PRIMARY | ALTERNATE | CONTINGENCY | EMERGENCY |
|---|---|---|---|---|
| **Provider** (bedside) | Standard care per JTS CPG; full surgical capability; component blood per MTP; routine documentation | Pre-briefed substitutions; LTOWB if components short; capability conserved by item-level discipline | Reverse triage active; withdraw advanced care per protocol; allocation framework anchors decisions | Survivability care only; pre-briefed boundaries; document for recovery |
| **Command** (CO/CMO) | Green on COP; standard authorities; no deviation from CPG; routine BUB reporting | Yellow on COP; substitution brief filed; CMO informs CO; trigger thresholds armed | Red on COP; CO/CMO activates allocation authority; pre-designated decision-maker engaged | Black on COP; CO/CMO pre-brief in full effect; recovery triggers actively monitored |
| **Logistics** | Routine resupply request; Class VIII < 24 h cycle; cold chain intact; no prioritization needed | Targeted request for named shortfall items; aerial resupply assessed; **walking blood bank activated** | Critical asset request; priority on evac corridor; triggers communicate exact capability needed; cross-loading evaluated | No outbound request possible; operating autonomously; recovery cued to first restored channel |
| **Higher echelon** | Routine SITREP cycle; standard sustainment; QI tracking continues | Notification of substitution posture; resupply queue updated; assess theater spread | Critical asset request actioned; evac corridor priority adjusted; adjacent units assessed for cross-leveling | Pre-briefed contingency plan executes; recovery operations prepared; theater-level reallocation if feasible |

## Worked vignette (96-hour Role 2 Light, EABO posture)

`PRIMARY → ALTERNATE → CONTINGENCY → ALTERNATE → PRIMARY`

- **T+0 Baseline** — EABO posture, Role 2L, Class VIII < 24 h cycle, CASEVAC corridor intact, full T/O dual surgical teams. → **PRIMARY**
- **T+18 h Trigger** — Adversary interdiction extends MEDEVAC corridor transit by 6 h; resupply window slips past 24 h. → **PRIMARY → ALTERNATE**
- **T+24 h Action** — Pre-briefed substitutions: LTOWB replaces components; CMO files substitution brief; Yellow on COP; targeted resupply request for component blood.
- **T+36 h Trigger** — MASCAL: 14 casualties (8 priority, 4 urgent); patient load exceeds throughput capacity; resupply still interdicted. → **ALTERNATE → CONTINGENCY**
- **T+42 h Action** — CO/CMO activates pre-designated allocation authority; reverse triage engaged; critical asset request to higher.
- **T+60 h Sustained** — Operating in CONTINGENCY for 24 h; QI tracking continues against JTS CPGs; provider moral burden contained by pre-briefed authority.
- **T+78 h Recovery** — Higher-echelon escort restores partial corridor; resupply window < 72 h; MASCAL load processed. → **CONTINGENCY → ALTERNATE**
- **T+90 h Full recovery** — Resupply < 24 h restored; CMO downgrades brief; Green on COP. → **ALTERNATE → PRIMARY**; full QI review begins.

## Application in the Role 2 Exercise Builder

The exercise builder already computes the strain signals these triggers key on. The recommended
Role 2 PACE state is derived on the **running MSEL timeline** from:

| PACE trigger | Exercise-computed signal |
|---|---|
| Class VIII / blood (component → LTOWB → residual) | LTOWB ledger: on-hand stock, walking-blood-bank activation, cumulative shortfall |
| Evac slipping / non-functional / no movement | Parameter-driven POI→Role 2 transit (threat posture × terrain) |
| MASCAL > throughput | Concurrent Role 2 census (arrival→cleared windows) vs capacity, during a MASCAL |
| Staff billets gapped | Surgical staffing from `specialists` (dual vs single surgical team) |

Signals not yet modeled in the exercise (resupply clock in hours, comms loss) are candidates for
a future config input or a scenario inject; until then the logistics posture is inferred from the
threat level (contested logistics is Assumption 1 of the framework).

## Source files in this folder

- `CSC_PACE_Framework_OnePager.docx` — the one-page framework (PACE table, assumptions, benefits).
- `Crisis_Standards_MM_Draft_Outline.docx` — Military Medicine manuscript outline (operational/moral/ethical imperative).
- `CSC_PACE_References.docx` — annotated supporting references.
- `CSC_PACE_NASEM_Deck_BSF.pptx`, `CSC_PACE_NASEM_Deck.pptx` — NASEM briefing decks.

## Selected references

- Institute of Medicine. *Crisis Standards of Care: A Systems Framework for Catastrophic Disaster Response.* National Academies Press; 2012. (Foundational conventional/contingency/crisis tier structure.)
- Hick JL, et al. *Duty to plan* (NAM Perspectives, 2020) — foreseeable scarcity creates an institutional obligation to pre-establish allocation principles.
- Joint Trauma System Clinical Practice Guidelines — Damage Control Resuscitation in Prolonged Field Care (CPG ID:73); Austere Resuscitative and Surgical Care (ARSC, CPG ID:76). Tiered "minimum / better / best" guidance.
- Gurney JM, et al. *Casualty Care Implications of Large-Scale Combat Operations.* J Trauma Acute Care Surg. 2023.
- Spruce MW, et al. *Justice and Triage in Military Medical Ethics.* J Trauma Acute Care Surg. 2025.
- Litz BT, et al. *Moral Injury and Moral Repair in War Veterans.* Clin Psychol Rev. 2009.
- Trichilo et al. *Moral injury and distress in deployed Role 2 surgeons.* JAMA Network Open, 2023.

*See `CSC_PACE_References.docx` for the complete annotated list.*
