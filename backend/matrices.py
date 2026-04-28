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
    "Humanitarian Assistance": 0.20,
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

ETIOLOGY_BY_SETTING: Dict[str, List[str]] = {
    "Frontal Attack":          ["GSW/Small Arms", "Indirect Fire/Mortar", "IED/Blast"],
    "Amphibious Assault":      ["Drowning (Amphibious)", "GSW/Small Arms", "IED/Blast", "Vehicle Rollover"],
    "Convoy Operations":       ["IED/Blast", "Vehicle Rollover", "GSW/Small Arms", "VBIED"],
    "Defensive Operations":    ["Indirect Fire/Mortar", "GSW/Small Arms", "IED/Blast"],
    "Retrograde Operations":   ["IED/Blast", "Vehicle Rollover", "Indirect Fire/Mortar"],
    "Stability Operations":    ["IED/Blast", "GSW/Small Arms", "VBIED"],
    "Humanitarian Assistance": ["Vehicle Rollover", "Structural Collapse", "Burns/Fire"],
}

# Trauma mechanism flavor by environment. Stacks with ETIOLOGY_BY_SETTING.
ENVIRONMENT_TRAUMA_FLAVOR: Dict[str, List[str]] = {
    "Desert":   ["Vehicle Rollover", "Burns/Fire"],
    "Jungle":   ["Structural Collapse", "Drowning (Amphibious)"],
    "Arctic":   [],
    "Mountain": ["Structural Collapse"],
    "Maritime": ["Drowning (Amphibious)", "Aviation Mishap"],
    "Littoral": ["Drowning (Amphibious)"],
    "Urban":    ["Structural Collapse", "VBIED"],
    "General":  [],
}


# ---------------------------------------------------------------------------
# DNBI by environment and region
# ---------------------------------------------------------------------------
# Existing DNBI_BY_ENVIRONMENT lives in main.py; reproduced here for the
# planner. Trim duplicates when main.py is refactored to import from here.

DNBI_BY_ENVIRONMENT: Dict[str, List[str]] = {
    "Jungle":   ["Dengue hemorrhagic fever", "Malaria", "Snake envenomation",
                 "Cellulitis", "Heat exhaustion", "Leptospirosis"],
    "Desert":   ["Heat stroke", "Severe dehydration", "Scorpion envenomation",
                 "Sand fly fever", "Rhabdomyolysis"],
    "Arctic":   ["Severe frostbite", "Hypothermia", "Trench foot", "Cold urticaria"],
    "Maritime": ["Near-drowning", "Decompression sickness",
                 "Marine envenomation", "Saltwater aspiration"],
    "Urban":    ["Crush injury", "Smoke inhalation", "MSK overuse", "CO poisoning"],
    "Mountain": ["HAPE", "HACE", "Acute mountain sickness", "Fall with fractures"],
    "Littoral": ["Near-drowning", "Jellyfish envenomation",
                 "Coral cuts with infection", "Heat exhaustion"],
    "General":  ["Combat stress reaction", "Dental emergency",
                 "Acute appendicitis", "Kidney stones",
                 "Pneumonia", "Gastroenteritis"],
}

# Region adds endemic / theater-specific patterns on top of environment DNBI.
# DRAFT — confirm against current intel/medical theater estimates.
DNBI_BY_REGION: Dict[str, List[str]] = {
    "CENTCOM":   ["Cutaneous leishmaniasis", "Q fever", "MERS-CoV exposure",
                  "Acute viral hepatitis"],
    "INDOPACOM": ["Japanese encephalitis", "Scrub typhus",
                  "Plasmodium vivax malaria", "Melioidosis"],
    "AFRICOM":   ["Falciparum malaria", "Lassa fever exposure",
                  "Schistosomiasis", "Typhoid"],
    "EUCOM":     ["Tick-borne encephalitis", "Lyme disease", "Hantavirus"],
    "SOUTHCOM":  ["Dengue", "Chagas exposure", "Zika"],
    "NORTHCOM":  ["Seasonal influenza", "Rocky Mountain spotted fever"],
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
# DRAFT — canonical MET list pending from user. Each MET maps to a list of
# boost hints (etiology or category strings) the planner uses to weight
# selection. Unknown METs are silently ignored.

MET_BIAS: Dict[str, List[str]] = {
    "Conduct Damage Control Surgery":        ["surgical"],
    "Conduct Damage Control Resuscitation":  ["surgical", "T1"],
    "Manage MASCAL":                         ["IED/Blast", "VBIED", "T1"],
    "Conduct Patient Movement":              ["evac"],
    "Provide Prolonged Casualty Care":       ["PCC"],
    "Treat CBRN Casualties":                 ["cbrn"],
    "Provide Behavioral Health Support":     ["Combat stress reaction"],
    "Provide Dental Care":                   ["Dental emergency"],
    "Manage Detainee Healthcare":            ["detainee"],
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
}
