"""
Default casualty-mix matrices.

DRAFT — pending SME review. Values here turn raw exercise inputs into a
deterministic per-day casualty plan. They are intentionally separated from the
case generator so they can be reviewed, tuned, and eventually overridden from
the UI (Phase 6) without touching code.

All percentages are expressed as fractions in [0.0, 1.0].
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# Trauma : DNBI ratio
# ---------------------------------------------------------------------------
# Base fraction of patients on a given day that are trauma (vs DNBI), by
# tactical_setting. MASCAL toggles override these to MASCAL_TRAUMA_RATIO for
# the MASCAL wave. threat_level then shifts the ratio (see THREAT_LEVEL_SHIFT).

TRAUMA_RATIO_BY_SETTING: Dict[str, float] = {
    "Frontal Attack":         0.80,
    "Amphibious Assault":     0.75,
    "Convoy Operations":      0.65,
    "Defensive Operations":   0.55,
    "Retrograde Operations":  0.60,
    "Stability Operations":   0.40,
    "Humanitarian Assistance": 0.30,  # Reviewer 29APR2026: bumped from 0.20.
}

DEFAULT_TRAUMA_RATIO = 0.50

MASCAL_TRAUMA_RATIO = 0.90

# threat_level → (trauma_ratio_delta, t1_pp_delta, t3_pp_delta)
# Positive t1_pp shifts severity up (more T1, less T3). Applied as percentage
# points on the triage distribution.
THREAT_LEVEL_SHIFT: Dict[str, Dict[str, float]] = {
    "Low":       {"trauma_ratio": -0.15, "t1_pp": -0.10, "t3_pp": +0.10},
    "Medium":    {"trauma_ratio":  0.00, "t1_pp":  0.00, "t3_pp":  0.00},
    "High":      {"trauma_ratio": +0.10, "t1_pp": +0.10, "t3_pp": -0.10},
}

# Night ops compresses MEDEVAC and degrades pre-hospital care, so cases
# present worse: shift T3 share into T1/T2.
NIGHT_OPS_TRIAGE_SHIFT = {"t1_pp": +0.05, "t2_pp": +0.05, "t3_pp": -0.10, "t4_pp": 0.0}

TRAUMA_RATIO_BOUNDS = (0.0, 0.95)


# ---------------------------------------------------------------------------
# Triage distribution targets (T1/T2/T3/T4 fractions, must sum to 1.0)
# ---------------------------------------------------------------------------
# Per-setting baseline distribution. MASCAL_TRIAGE_DISTRIBUTION overrides for
# the MASCAL wave. THREAT_LEVEL_SHIFT and NIGHT_OPS_TRIAGE_SHIFT apply on top.

BASE_TRIAGE_DISTRIBUTION: Dict[str, Dict[str, float]] = {
    "Frontal Attack":          {"T1": 0.25, "T2": 0.40, "T3": 0.30, "T4": 0.05},
    "Amphibious Assault":      {"T1": 0.25, "T2": 0.40, "T3": 0.30, "T4": 0.05},
    "Convoy Operations":       {"T1": 0.20, "T2": 0.35, "T3": 0.40, "T4": 0.05},
    "Defensive Operations":    {"T1": 0.15, "T2": 0.35, "T3": 0.40, "T4": 0.10},
    "Retrograde Operations":   {"T1": 0.15, "T2": 0.35, "T3": 0.40, "T4": 0.10},
    "Stability Operations":    {"T1": 0.10, "T2": 0.30, "T3": 0.50, "T4": 0.10},
    "Humanitarian Assistance": {"T1": 0.05, "T2": 0.25, "T3": 0.55, "T4": 0.15},
}

DEFAULT_TRIAGE_DISTRIBUTION = {"T1": 0.15, "T2": 0.35, "T3": 0.40, "T4": 0.10}

MASCAL_TRIAGE_DISTRIBUTION = {"T1": 0.30, "T2": 0.40, "T3": 0.25, "T4": 0.05}


# ---------------------------------------------------------------------------
# Etiology preferences (the mechanism passed to the case generator)
# ---------------------------------------------------------------------------
# Each tactical_setting has an ordered list of characteristic etiologies. The
# planner samples from this list (weighted toward the front) for trauma cases
# on non-MASCAL days. On MASCAL days, mascal_etiology dominates.

# Reviewer 29APR2026: "Fragmentation Drones" added to every setting at the front
# of the pool — current OEF / Ukraine theater dominated by FPV / fragmentation
# UAS munitions. Frontal Attack additionally gets it weighted heavier upstream
# (the planner samples from the front of the list).
ETIOLOGY_BY_SETTING: Dict[str, List[str]] = {
    "Frontal Attack":          ["Fragmentation Drones", "GSW/Small Arms", "Indirect Fire/Mortar", "IED/Blast"],
    "Amphibious Assault":      ["Fragmentation Drones", "Drowning (Amphibious)", "GSW/Small Arms", "IED/Blast", "Vehicle Rollover"],
    "Convoy Operations":       ["Fragmentation Drones", "IED/Blast", "Vehicle Rollover", "GSW/Small Arms", "VBIED"],
    "Defensive Operations":    ["Fragmentation Drones", "Indirect Fire/Mortar", "GSW/Small Arms", "IED/Blast"],
    "Retrograde Operations":   ["Fragmentation Drones", "IED/Blast", "Vehicle Rollover", "Indirect Fire/Mortar"],
    "Stability Operations":    ["Fragmentation Drones", "IED/Blast", "GSW/Small Arms", "VBIED"],
    "Humanitarian Assistance": ["Fragmentation Drones", "Vehicle Rollover", "Structural Collapse", "Burns/Fire"],
}

# Trauma mechanism flavor by environment. Stacks with ETIOLOGY_BY_SETTING.
# Reviewer 29APR2026: Arctic + General gain "Fragmentation Drones" — UAS reach
# is environment-agnostic, so flavor it everywhere even when there's no other
# environmental mechanism.
ENVIRONMENT_TRAUMA_FLAVOR: Dict[str, List[str]] = {
    "Desert":   ["Vehicle Rollover", "Burns/Fire"],
    "Jungle":   ["Structural Collapse", "Drowning (Amphibious)"],
    "Arctic":   ["Fragmentation Drones"],
    "Mountain": ["Structural Collapse"],
    "Maritime": ["Drowning (Amphibious)", "Aviation Mishap"],
    "Littoral": ["Drowning (Amphibious)"],
    "Urban":    ["Structural Collapse", "VBIED"],
    "General":  ["Fragmentation Drones"],
}


# ---------------------------------------------------------------------------
# DNBI by environment and region
# ---------------------------------------------------------------------------
# Existing DNBI_BY_ENVIRONMENT lives in main.py; reproduced here for the
# planner. Trim duplicates when main.py is refactored to import from here.

# Reviewer 29APR2026: broaden environment DNBI with a mix of severities (mild
# T3/T4 candidates through severe T1/T2 candidates), per "use a variety of
# severities" review note. Original entries kept; additions append.
DNBI_BY_ENVIRONMENT: Dict[str, List[str]] = {
    "Jungle":   ["Dengue hemorrhagic fever", "Malaria", "Snake envenomation",
                 "Cellulitis", "Heat exhaustion", "Leptospirosis",
                 "Severe falciparum malaria with cerebral involvement",
                 "Cellulitis with abscess formation", "Tropical pyomyositis"],
    "Desert":   ["Heat stroke", "Severe dehydration", "Scorpion envenomation",
                 "Sand fly fever", "Rhabdomyolysis",
                 "Severe rhabdomyolysis with acute kidney injury",
                 "Mild heat exhaustion", "Acute upper respiratory infection (dust)"],
    "Arctic":   ["Severe frostbite", "Hypothermia", "Trench foot", "Cold urticaria",
                 "Severe hypothermia with cardiac instability",
                 "Snow blindness", "CO poisoning from snow shelter"],
    "Maritime": ["Near-drowning", "Decompression sickness",
                 "Marine envenomation", "Saltwater aspiration",
                 "Severe marine envenomation with anaphylaxis",
                 "Otitis externa", "Mild seasickness"],
    "Urban":    ["Crush injury", "Smoke inhalation", "MSK overuse", "CO poisoning",
                 "Severe smoke inhalation with airway burn",
                 "Acute viral gastroenteritis (outbreak)",
                 "Acute psychiatric crisis (urban combat)"],
    "Mountain": ["HAPE", "HACE", "Acute mountain sickness", "Fall with fractures",
                 "Severe HACE with herniation risk",
                 "Mild AMS responsive to descent", "Frostbite of digits"],
    "Littoral": ["Near-drowning", "Jellyfish envenomation",
                 "Coral cuts with infection", "Heat exhaustion",
                 "Severe bacterial wound infection from coral abrasion",
                 "Mild jellyfish sting"],
    "General":  ["Combat stress reaction", "Dental emergency",
                 "Acute appendicitis", "Kidney stones",
                 "Pneumonia", "Gastroenteritis",
                 "Severe sepsis from urinary source",
                 "Acute psychiatric emergency", "Diabetic ketoacidosis"],
}

# Region adds endemic / theater-specific patterns on top of environment DNBI.
# Reviewer 29APR2026: same broaden-with-severity treatment as environment DNBI.
DNBI_BY_REGION: Dict[str, List[str]] = {
    "CENTCOM":   ["Cutaneous leishmaniasis", "Q fever", "MERS-CoV exposure",
                  "Acute viral hepatitis",
                  "Severe sand fly fever", "Brucellosis"],
    "INDOPACOM": ["Japanese encephalitis", "Scrub typhus",
                  "Plasmodium vivax malaria", "Melioidosis",
                  "Severe scrub typhus with multiorgan failure",
                  "Tsutsugamushi disease (mild presentation)"],
    "AFRICOM":   ["Falciparum malaria", "Lassa fever exposure",
                  "Schistosomiasis", "Typhoid",
                  "Severe falciparum malaria with cerebral involvement",
                  "Yellow fever (severe)"],
    "EUCOM":     ["Tick-borne encephalitis", "Lyme disease", "Hantavirus",
                  "Severe Lyme disease with cardiac involvement",
                  "Tularemia"],
    "SOUTHCOM":  ["Dengue", "Chagas exposure", "Zika",
                  "Severe leptospirosis (Weil's disease)",
                  "Yellow fever"],
    "NORTHCOM":  ["Seasonal influenza", "Rocky Mountain spotted fever",
                  "West Nile virus", "Lyme disease"],
}


# ---------------------------------------------------------------------------
# Trauma injury menus (existing main.py tables, reproduced for the planner)
# ---------------------------------------------------------------------------

TRAUMA_BY_ETIOLOGY: Dict[str, List[str]] = {
    "IED/Blast":              ["Traumatic bilateral lower extremity amputation",
                               "TBI with penetrating fragment", "Blast lung injury",
                               "Penetrating abdominal trauma with evisceration",
                               "Severe burns with blast injury"],
    "Vehicle Rollover":       ["Blunt abdominal trauma with splenic laceration",
                               "C-spine fracture", "Bilateral femur fractures",
                               "Flail chest", "Pelvic fracture with hemorrhage"],
    "GSW/Small Arms":         ["Penetrating chest trauma with hemothorax",
                               "GSW abdomen with liver laceration",
                               "GSW extremity with vascular injury",
                               "GSW neck with airway compromise"],
    "Aviation Mishap":        ["Multi-system blunt trauma",
                               "Severe burns (>40% TBSA)",
                               "Spinal cord injury", "Traumatic brain injury"],
    "Indirect Fire/Mortar":   ["Multiple penetrating fragment wounds",
                               "TBI from blast", "Traumatic amputation",
                               "Penetrating eye injury"],
    "Structural Collapse":    ["Crush syndrome", "Compartment syndrome",
                               "Traumatic asphyxiation",
                               "Multiple long bone fractures"],
    "Burns/Fire":             ["Severe thermal burns (>30% TBSA)",
                               "Inhalation injury", "CO poisoning",
                               "Facial burns with airway compromise"],
    "Drowning (Amphibious)":  ["Near-drowning with aspiration",
                               "Hypothermia with near-drowning",
                               "Trauma from vessel impact"],
    "VBIED":                  ["Multi-system blast trauma",
                               "Severe burns with TBI",
                               "Traumatic amputation bilateral",
                               "Penetrating torso wounds"],
    # Reviewer 29APR2026: small-munition UAS injury pattern — predominantly
    # penetrating fragments to face/neck/torso, FPV-targeted limb amputations
    # against exposed personnel, and TBI from proximate detonation.
    "Fragmentation Drones":   ["Multiple penetrating fragment wounds (face/neck)",
                               "Traumatic amputation of digits/hand from FPV strike",
                               "Penetrating eye injury with globe rupture",
                               "TBI from proximate drone detonation",
                               "Penetrating thoracic injury with hemothorax",
                               "Severe shrapnel wounds to extremities with vascular injury"],
}

GENERAL_TRAUMA: List[str] = [
    "GSW right thigh with femoral artery injury",
    "Penetrating abdominal trauma",
    "Blunt chest trauma with rib fractures",
    "Open tibia-fibula fracture",
    "Traumatic brain injury - moderate",
    "Blast injury with TM rupture",
    "Penetrating neck trauma",
    "GSW chest with pneumothorax",
    "Pelvic fracture - stable",
    "Burn injury 15% TBSA",
]


# ---------------------------------------------------------------------------
# CBRN and detainee
# ---------------------------------------------------------------------------
# CBRN day allocation: ~20% of trauma budget becomes CBRN cases (configurable).
CBRN_TRAUMA_BUDGET_FRACTION = 0.20

CBRN_ETIOLOGIES: Dict[str, List[str]] = {
    "Nerve Agent":        ["Sarin exposure with cholinergic crisis",
                           "VX exposure", "Organophosphate poisoning"],
    "Blister Agent":      ["Mustard gas exposure with airway compromise",
                           "Lewisite exposure"],
    "Blood Agent":        ["Cyanide exposure with metabolic acidosis"],
    "Pulmonary Agent":    ["Chlorine inhalation with ARDS",
                           "Phosgene exposure"],
    "Radiation":          ["Acute radiation syndrome",
                           "Combined injury (trauma + radiation)"],
    "Biological":         ["Anthrax exposure (cutaneous)",
                           "Plague exposure (pneumonic)"],
    "Decontamination":    ["Hyperthermia during decon",
                           "Decon failure with persistent contamination"],
}

# Detainee day allocation: ~12% of patients on detainee_ops days are detainees.
DETAINEE_BUDGET_FRACTION = 0.12

DETAINEE_CASE_TYPES: List[str] = [
    "Detainee with combat trauma (GSW)",
    "Detainee with chronic infectious disease (TB)",
    "Detainee under hunger strike",
    "Detainee with self-inflicted injury",
    "Detainee with untreated chronic illness",
    "Detainee acute psychiatric crisis",
]


# ---------------------------------------------------------------------------
# Footprint capability detection
# ---------------------------------------------------------------------------
# Substring matches (case-insensitive) on the entries of selected_footprint.

SURGICAL_FOOTPRINT_KEYWORDS = [
    "surgical team", "frss", "forward resuscitative surgical",
    "operating room", "anesthesia", "scrub tech", "surgeon",
]

BLOOD_FOOTPRINT_KEYWORDS = [
    "whole blood", "blood products", "walking blood bank", "wbb", "ldwb",
]

ICU_FOOTPRINT_KEYWORDS = [
    "icu", "intensive care", "holding", "pcc",
]


# ---------------------------------------------------------------------------
# MET → case bias hints
# ---------------------------------------------------------------------------
# Keys here match the Tier 1 Battalion Core METL from NAVMC 3500.84A
# (Ch.2 ¶2000), aligned with the frontend's MET_DATA (src/app/page.tsx).
#
# Each MET maps to a list of boost tags (etiology / category / triage code)
# the planner uses to weight case selection when that MET is in `selected_mets`.
# Unknown METs are silently ignored.
#
# The full canonical list — Tier 2 collective events (HSS-OPS-*, HSS-PLAN-*,
# HSS-SVCS-*) and Tier 3 individual events (HSS-MED-*, 8404-HSS-*, CLIN-HSS-*)
# — lives in `docs/FOR_REVIEW_matrices_and_mets.md` §16 for reference; only
# the Tier 1 set is wired into the planner today, since those are what the UI
# exposes as MET checkboxes.

MET_BIAS: Dict[str, List[str]] = {
    # Tier 1 — Battalion Core METL (NAVMC 3500.84A Ch.2 ¶2000)
    "Provide Task-Organized Forces":        [],                                    # MCT 1.1.2 — planning, no case bias
    "Support Amphibious Operations":        ["Drowning (Amphibious)"],             # MCT 1.12.2
    "Conduct Casualty Treatment":           ["surgical", "T1"],                    # MCT 4.5.3
    "Conduct Temporary Casualty Holding":   ["PCC"],                               # MCT 4.5.4
    "Conduct Casualty Evacuation":          ["evac"],                              # MCT 4.5.5
    "Conduct Mass Casualty Operations":     ["IED/Blast", "VBIED", "Fragmentation Drones", "T1"],  # MCT 4.5.6
    "Conduct and Provide Dental Services":  ["Dental emergency"],                  # MCT 4.5.7
    "Conduct Medical Regulating Services":  ["evac"],                              # MCT 4.5.8
}


# ---------------------------------------------------------------------------
# Phase derivation (replaces keyword matching)
# ---------------------------------------------------------------------------
# Cases that need surgery use DCR + DCS + PCC; medical/DNBI use DCR + PCC only.
# Keyed by a category tag the planner attaches to each etiology bucket so the
# generator doesn't have to re-derive from free text.

PHASES_BY_CATEGORY = {
    "trauma_surgical":     ["DCR", "DCS", "PCC"],
    "trauma_non_surgical": ["DCR", "PCC"],
    "dnbi":                ["DCR", "PCC"],
    "cbrn":                ["DCR", "PCC"],   # most CBRN is medical; surgical CBRN escalates
    "cbrn_combined":       ["DCR", "DCS", "PCC"],
    "detainee_trauma":     ["DCR", "DCS", "PCC"],
    "detainee_medical":    ["DCR", "PCC"],
}

# Etiologies whose injury patterns are predominantly surgical when classified
# as trauma. Used by the planner to pick trauma_surgical vs trauma_non_surgical.
SURGICAL_ETIOLOGIES = {
    "IED/Blast", "VBIED", "GSW/Small Arms", "Vehicle Rollover",
    "Aviation Mishap", "Structural Collapse",
    "Fragmentation Drones",  # Reviewer 29APR2026: predominantly fragment / amputation patterns.
}
