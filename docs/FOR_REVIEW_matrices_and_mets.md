# FOR REVIEW — Matrices and METs

**Status:** awaiting SME / user review.
**Source of truth today:** `backend/matrices.py` (numeric defaults), `backend/preset_data/*.json` (preset bundles).

## How to use this document

1. Edit values **in place** in the tables below. Markdown tables are fine — keep the column shape, change the numbers / list entries.
2. For sections marked **CANONICAL — please supply**, fill in the missing list.
3. Add free-text notes under "Reviewer notes" lines.
4. When finished, commit your edits (or just say "done") and tell Claude to apply them. Claude will translate the edits into changes to `matrices.py` and the preset JSONs and re-run tests.

Validation rules Claude will enforce when applying edits:
- Triage distributions must sum to **1.0** (T1+T2+T3+T4).
- All ratios are in **[0.0, 1.0]**.
- Threat-level shift keys are limited to: `trauma_ratio`, `t1_pp`, `t2_pp`, `t3_pp`, `t4_pp`.

---

## 1. Trauma : DNBI ratio per tactical setting

Fraction of patients on a given day that are trauma (vs DNBI), before threat-level / MASCAL adjustments.

| Tactical setting       | Trauma ratio |
|------------------------|--------------|
| Frontal Attack         | 0.80         |
| Amphibious Assault     | 0.75         |
| Convoy Operations      | 0.65         |
| Defensive Operations   | 0.55         |
| Retrograde Operations  | 0.60         |
| Stability Operations   | 0.40         |
| Humanitarian Assistance| 0.20         |

Other related constants:
- `DEFAULT_TRAUMA_RATIO` (fallback for unknown settings) = **0.50**
- `MASCAL_TRAUMA_RATIO` (overrides on MASCAL day) = **0.90**
- `TRAUMA_RATIO_BOUNDS` (clamp) = **(0.0, 0.95)**

**Reviewer notes:**
_(write here — e.g. "Defensive Operations should be 0.50, not 0.55, in low-intensity contingency")_

---

## 2. Threat level shift

Deltas applied on top of the base ratio + base triage distribution. `t*_pp` are percentage points; positive shifts severity up.

| Level   | trauma_ratio | t1_pp | t2_pp | t3_pp | t4_pp |
|---------|--------------|-------|-------|-------|-------|
| Low     | -0.15        | -0.10 |  0.00 | +0.10 |  0.00 |
| Medium  |  0.00        |  0.00 |  0.00 |  0.00 |  0.00 |
| High    | +0.10        | +0.10 |  0.00 | -0.10 |  0.00 |

**Reviewer notes:**
_(write here)_

---

## 3. Base triage distribution per tactical setting

Each row must sum to 1.0.

| Tactical setting        | T1   | T2   | T3   | T4   |
|-------------------------|------|------|------|------|
| Frontal Attack          | 0.25 | 0.40 | 0.30 | 0.05 |
| Amphibious Assault      | 0.25 | 0.40 | 0.30 | 0.05 |
| Convoy Operations       | 0.20 | 0.35 | 0.40 | 0.05 |
| Defensive Operations    | 0.15 | 0.35 | 0.40 | 0.10 |
| Retrograde Operations   | 0.15 | 0.35 | 0.40 | 0.10 |
| Stability Operations    | 0.10 | 0.30 | 0.50 | 0.10 |
| Humanitarian Assistance | 0.05 | 0.25 | 0.55 | 0.15 |

`DEFAULT_TRIAGE_DISTRIBUTION` = `{T1: 0.15, T2: 0.35, T3: 0.40, T4: 0.10}`

**Reviewer notes:**
_(write here)_

---

## 4. MASCAL triage distribution

Applied on MASCAL days. Must sum to 1.0.

| T1   | T2   | T3   | T4   |
|------|------|------|------|
| 0.30 | 0.40 | 0.25 | 0.05 |

**Reviewer notes:**
_(write here)_

---

## 5. Night-ops triage shift

Compresses MEDEVAC, degrades pre-hospital — pushes T3 share into T1/T2.

| t1_pp | t2_pp | t3_pp | t4_pp |
|-------|-------|-------|-------|
| +0.05 | +0.05 | -0.10 |  0.00 |

**Reviewer notes:**
_(write here)_

---

## 6. CBRN and detainee day allocation

- `CBRN_TRAUMA_BUDGET_FRACTION` = **0.20** (fraction of remaining trauma budget that becomes CBRN cases on a CBRN day)
- `DETAINEE_BUDGET_FRACTION` = **0.12** (fraction of remaining patients that are detainees on a detainee-ops day)

**Reviewer notes:**
_(write here)_

---

## 7. Etiology pool by tactical setting

Mechanisms sampled (weighted toward the front) for trauma cases. MASCAL day overrides with `mascal_etiology`.

| Tactical setting        | Etiology pool (in order) |
|-------------------------|--------------------------|
| Frontal Attack          | GSW/Small Arms; Indirect Fire/Mortar; IED/Blast |
| Amphibious Assault      | Drowning (Amphibious); GSW/Small Arms; IED/Blast; Vehicle Rollover |
| Convoy Operations       | IED/Blast; Vehicle Rollover; GSW/Small Arms; VBIED |
| Defensive Operations    | Indirect Fire/Mortar; GSW/Small Arms; IED/Blast |
| Retrograde Operations   | IED/Blast; Vehicle Rollover; Indirect Fire/Mortar |
| Stability Operations    | IED/Blast; GSW/Small Arms; VBIED |
| Humanitarian Assistance | Vehicle Rollover; Structural Collapse; Burns/Fire |

**Reviewer notes:**
_(write here)_

---

## 8. Environment trauma flavor

Stacks on top of setting etiologies. Adds environmental flavor to mechanism choice.

| Environment | Flavor etiologies |
|-------------|-------------------|
| Desert      | Vehicle Rollover; Burns/Fire |
| Jungle      | Structural Collapse; Drowning (Amphibious) |
| Arctic      | _(none)_ |
| Mountain    | Structural Collapse |
| Maritime    | Drowning (Amphibious); Aviation Mishap |
| Littoral    | Drowning (Amphibious) |
| Urban       | Structural Collapse; VBIED |
| General     | _(none)_ |

**Reviewer notes:**
_(write here)_

---

## 9. DNBI by environment

| Environment | DNBI items |
|-------------|------------|
| Jungle    | Dengue hemorrhagic fever; Malaria; Snake envenomation; Cellulitis; Heat exhaustion; Leptospirosis |
| Desert    | Heat stroke; Severe dehydration; Scorpion envenomation; Sand fly fever; Rhabdomyolysis |
| Arctic    | Severe frostbite; Hypothermia; Trench foot; Cold urticaria |
| Maritime  | Near-drowning; Decompression sickness; Marine envenomation; Saltwater aspiration |
| Urban     | Crush injury; Smoke inhalation; MSK overuse; CO poisoning |
| Mountain  | HAPE; HACE; Acute mountain sickness; Fall with fractures |
| Littoral  | Near-drowning; Jellyfish envenomation; Coral cuts with infection; Heat exhaustion |
| General   | Combat stress reaction; Dental emergency; Acute appendicitis; Kidney stones; Pneumonia; Gastroenteritis |

**Reviewer notes:**
_(write here)_

---

## 10. DNBI by region (theater-endemic)

Stacks on top of environment DNBI.

| Region    | DNBI items |
|-----------|------------|
| CENTCOM   | Cutaneous leishmaniasis; Q fever; MERS-CoV exposure; Acute viral hepatitis |
| INDOPACOM | Japanese encephalitis; Scrub typhus; Plasmodium vivax malaria; Melioidosis |
| AFRICOM   | Falciparum malaria; Lassa fever exposure; Schistosomiasis; Typhoid |
| EUCOM     | Tick-borne encephalitis; Lyme disease; Hantavirus |
| SOUTHCOM  | Dengue; Chagas exposure; Zika |
| NORTHCOM  | Seasonal influenza; Rocky Mountain spotted fever |

**Reviewer notes:**
_(write here)_

---

## 11. Trauma injury menus per etiology

The case generator picks one of these as `case_type` based on the planner-chosen etiology.

| Etiology              | Injuries |
|-----------------------|----------|
| IED/Blast             | Traumatic bilateral lower extremity amputation; TBI with penetrating fragment; Blast lung injury; Penetrating abdominal trauma with evisceration; Severe burns with blast injury |
| Vehicle Rollover      | Blunt abdominal trauma with splenic laceration; C-spine fracture; Bilateral femur fractures; Flail chest; Pelvic fracture with hemorrhage |
| GSW/Small Arms        | Penetrating chest trauma with hemothorax; GSW abdomen with liver laceration; GSW extremity with vascular injury; GSW neck with airway compromise |
| Aviation Mishap       | Multi-system blunt trauma; Severe burns (>40% TBSA); Spinal cord injury; Traumatic brain injury |
| Indirect Fire/Mortar  | Multiple penetrating fragment wounds; TBI from blast; Traumatic amputation; Penetrating eye injury |
| Structural Collapse   | Crush syndrome; Compartment syndrome; Traumatic asphyxiation; Multiple long bone fractures |
| Burns/Fire            | Severe thermal burns (>30% TBSA); Inhalation injury; CO poisoning; Facial burns with airway compromise |
| Drowning (Amphibious) | Near-drowning with aspiration; Hypothermia with near-drowning; Trauma from vessel impact |
| VBIED                 | Multi-system blast trauma; Severe burns with TBI; Traumatic amputation bilateral; Penetrating torso wounds |

**Reviewer notes:**
_(write here)_

---

## 12. General trauma fallback

Used when no etiology-specific menu hits.

- GSW right thigh with femoral artery injury
- Penetrating abdominal trauma
- Blunt chest trauma with rib fractures
- Open tibia-fibula fracture
- Traumatic brain injury - moderate
- Blast injury with TM rupture
- Penetrating neck trauma
- GSW chest with pneumothorax
- Pelvic fracture - stable
- Burn injury 15% TBSA

**Reviewer notes:**
_(write here)_

---

## 13. CBRN etiologies

| Category         | Cases |
|------------------|-------|
| Nerve Agent      | Sarin exposure with cholinergic crisis; VX exposure; Organophosphate poisoning |
| Blister Agent    | Mustard gas exposure with airway compromise; Lewisite exposure |
| Blood Agent      | Cyanide exposure with metabolic acidosis |
| Pulmonary Agent  | Chlorine inhalation with ARDS; Phosgene exposure |
| Radiation        | Acute radiation syndrome; Combined injury (trauma + radiation) |
| Biological       | Anthrax exposure (cutaneous); Plague exposure (pneumonic) |
| Decontamination  | Hyperthermia during decon; Decon failure with persistent contamination |

**Reviewer notes:**
_(write here)_

---

## 14. Detainee case types

- Detainee with combat trauma (GSW)
- Detainee with chronic infectious disease (TB)
- Detainee under hunger strike
- Detainee with self-inflicted injury
- Detainee with untreated chronic illness
- Detainee acute psychiatric crisis

**Reviewer notes:**
_(write here)_

---

## 15. Footprint keyword detection

Substring matches (case-insensitive) on `selected_footprint` items.

- **Surgical-capable footprint:** `surgical team`, `frss`, `forward resuscitative surgical`, `operating room`, `anesthesia`, `scrub tech`, `surgeon`
- **Blood-capable footprint:** `whole blood`, `blood products`, `walking blood bank`, `wbb`, `ldwb`
- **ICU / holding-capable footprint:** `icu`, `intensive care`, `holding`, `pcc`

**Reviewer notes:**
_(write here)_

---

## 16. CANONICAL — please supply: MET list

The current `MET_BIAS` table below is **illustrative only**. Replace with the canonical Role 2 / Mission Essential Task list. For each MET, list the etiology / category / triage tags it should boost (these influence which generated cases get flagged as exercising that MET).

### Canonical MET list (PLEASE FILL)

```
- MET 1: ____________________
- MET 2: ____________________
- MET 3: ____________________
...
```

### Current illustrative MET_BIAS (replace or annotate)

| MET                                      | Boost tags |
|------------------------------------------|------------|
| Conduct Damage Control Surgery           | surgical |
| Conduct Damage Control Resuscitation     | surgical; T1 |
| Manage MASCAL                            | IED/Blast; VBIED; T1 |
| Conduct Patient Movement                 | evac |
| Provide Prolonged Casualty Care          | PCC |
| Treat CBRN Casualties                    | cbrn |
| Provide Behavioral Health Support        | Combat stress reaction |
| Provide Dental Care                      | Dental emergency |
| Manage Detainee Healthcare               | detainee |

**Reviewer notes:**
_(write here)_

---

## 17. Preset bundles (review the non-default ones)

Three bundles ship in `backend/preset_data/`. The first is intentionally empty (acts as an explicit "factory defaults" anchor). The other two are DRAFT.

### `permissive_humanitarian.json` — Low-threat HA / DR

Overrides only the listed entries (everything else inherits defaults).

- `trauma_ratio_by_setting`: Humanitarian Assistance **0.10**, Stability Operations **0.30**, Defensive Operations **0.40**
- `threat_level_shift`:
  - Low: trauma_ratio **-0.20**, t1_pp **-0.12**, t3_pp **+0.12**
  - Medium: trauma_ratio **-0.05**, t1_pp **-0.05**, t3_pp **+0.05**
- `base_triage_distribution`:
  - Humanitarian Assistance: T1 **0.03**, T2 **0.20**, T3 **0.55**, T4 **0.22**
  - Stability Operations: T1 **0.07**, T2 **0.27**, T3 **0.50**, T4 **0.16**

**Reviewer notes:**
_(write here)_

### `high_intensity_contingency.json` — Near-peer combat

- `trauma_ratio_by_setting`: Frontal Attack **0.90**, Amphibious Assault **0.85**, Convoy Operations **0.78**, Defensive Operations **0.70**, Retrograde Operations **0.75**, Stability Operations **0.55**, Humanitarian Assistance **0.30**
- `threat_level_shift`:
  - Low: trauma_ratio **-0.05**, t1_pp **-0.05**, t3_pp **+0.05**
  - Medium: trauma_ratio **+0.05**, t1_pp **+0.05**, t3_pp **-0.05**
  - High: trauma_ratio **+0.15**, t1_pp **+0.15**, t3_pp **-0.15**
- `base_triage_distribution` (T1 / T2 / T3 / T4):
  - Frontal Attack: 0.32 / 0.42 / 0.22 / 0.04
  - Amphibious Assault: 0.30 / 0.42 / 0.24 / 0.04
  - Convoy Operations: 0.27 / 0.40 / 0.30 / 0.03
  - Defensive Operations: 0.22 / 0.40 / 0.32 / 0.06
  - Retrograde Operations: 0.22 / 0.40 / 0.32 / 0.06
  - Stability Operations: 0.15 / 0.35 / 0.42 / 0.08
  - Humanitarian Assistance: 0.08 / 0.30 / 0.50 / 0.12
- `mascal_triage_distribution`: T1 **0.35**, T2 **0.40**, T3 **0.20**, T4 **0.05**
- `etiology_by_setting`:
  - Frontal Attack: IED/Blast; Indirect Fire/Mortar; GSW/Small Arms; VBIED
  - Convoy Operations: IED/Blast; VBIED; Vehicle Rollover; GSW/Small Arms
  - Defensive Operations: Indirect Fire/Mortar; IED/Blast; GSW/Small Arms; VBIED

**Reviewer notes:**
_(write here)_

---

## Sign-off

When you're done editing this file:
- [ ] All "Reviewer notes" sections addressed (or explicitly marked "no change").
- [ ] Section 16 canonical MET list filled in.
- [ ] Tell Claude — Claude will translate edits into changes to `backend/matrices.py` and `backend/preset_data/*.json`, run the test suite, and commit.

_Reviewer:_ ____________________
_Date:_ ____________________
