"use client";
import React, { useState, useEffect } from 'react';
import Link from 'next/link';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://role2-builder-production.up.railway.app';

export default function SetupPage() {
  const [exerciseName, setExerciseName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [duration, setDuration] = useState(3);
  const [supportedUnit, setSupportedUnit] = useState("Division");

  // AOR expanded options
  const [environment, setEnvironment] = useState("Urban");
  const [threatLevel, setThreatLevel] = useState("Peer/Near-Peer");
  const [region, setRegion] = useState("Indo-Pacific");

  // MET selection
  const [selectedMETs, setSelectedMETs] = useState<string[]>([]);
  const [expandedMET, setExpandedMET] = useState<string | null>(null);

  // Footprint selection
  const [selectedFootprint, setSelectedFootprint] = useState<string[]>([]);

  // Specialist staffing (0-5 each)
  const [specialists, setSpecialists] = useState<Record<string, number>>({
    "ERC Nurse": 0,
    "ER Nurse": 0,
    "ICU Nurse": 0,
    "Med Surg Nurse": 0,
    "Family Physician": 0,
    "Emergency Medicine": 0,
    "General Surgery": 0,
    "Orthopaedic Surgery": 0,
    "Anesthesiology": 0,
  });

  // Environment options
  const ENVIRONMENTS = ["Urban", "Jungle", "Arctic", "Desert", "Maritime", "Mountain", "Littoral"];
  const THREAT_LEVELS = ["Peer/Near-Peer", "Irregular", "Hybrid", "HADR/Permissive"];
  const REGIONS = ["Indo-Pacific", "CENTCOM", "EUCOM", "AFRICOM", "SOUTHCOM", "NORTHCOM"];

  // Footprint components with associated event prefixes
  const FOOTPRINT = [
    { id: "STP", name: "Shock Trauma Platoon (STP)", events: ["HSS-STP"] },
    { id: "FRSS", name: "Forward Resuscitative Surgical System (FRSS)", events: ["HSS-FRSS"] },
    { id: "Holding", name: "Temporary Holding", events: ["HSS-SVCS-3502"] },
    { id: "MA", name: "Mortuary Affairs", events: [] },
    { id: "Lab", name: "Laboratory", events: [] },
    { id: "Radiology", name: "Radiology", events: [] },
    { id: "COC", name: "Combat Operations Center (COC)", events: ["HSS-OPS"] },
    { id: "Dental", name: "Dental", events: ["HSS-DENT"] },
  ];

  // Full MET data from NAVMC 3500.84A
  const MET_DATA = [
    {
      id: "MET 1",
      mctTask: "MCT 1.1.2",
      name: "Provide Task-Organized Forces",
      pecls: [
        "Conduct Problem Framing",
        "Determine planning process (Campaign, MCPP, R2P2, Hasty Planning)",
        "Determine Time Available",
        "Establish timeline for planning and preparation",
        "Issue Warning Order",
        "Implement Cultural Considerations into Mission Planning",
        "Create orders (OPORD, FRAGO, Decision Support Tools)",
        "Issue orders",
        "Implement feedback mechanisms",
        "Coordinate planning with higher, adjacent, subordinate, and supporting units",
      ],
      requiredFootprint: ["COC"],
    },
    {
      id: "MET 2",
      mctTask: "MCT 4.5.3",
      name: "Conduct Casualty Treatment",
      pecls: [
        "Provide forward resuscitative surgery system",
        "Provide Shock trauma platoons",
        "Provide temporary casualty holding",
        "Conduct triage",
        "Treat casualties",
        "Stabilize for evacuation",
        "Track casualties received",
        "Prepare casualty reports",
        "Identify lift requirements",
        "Move to location",
        "Employ tentage/equipment",
        "Establish communications",
        "Maintain capability for hasty retrograde",
        "Receive casualty evacuation request",
        "Determine means of casualty movement",
        "Determine casualty destination facility",
        "Coordinate with DASC for air support",
        "Track casualty movement",
        "Activate mass casualty plan",
        "Identify non-medical assets available to assist",
        "Provide emergency treatment",
        "Determine patient transportation requirements",
        "Establish communication for evacuation",
        "Reassess triage categories (NATO Casualty Categories)",
        "Evacuate casualties",
        "Conduct casualty turnover",
        "Triage (dental)",
        "Perform History/physical examination",
        "Identify injury/illness",
        "Render standard of care",
        "Utilize ancillary services as needed",
        "Document care",
        "Disposition patient",
        "Establish dental facility",
      ],
      requiredFootprint: ["STP", "FRSS", "Holding", "Dental"],
    },
    {
      id: "MET 3",
      mctTask: "MCT 4.5.4",
      name: "Conduct Temporary Casualty Holding",
      pecls: [
        "Assess casualty",
        "Provide holding capability/facilities until evacuation or discharge",
        "Maintain accountability of casualty and their gear",
        "Reassess casualty as needed",
        "Document treatment as necessary",
        "Prepare casualty for evacuation",
        "Organize battle staff",
        "Establish a COC",
        "Establish COC watch",
        "Maintain battle rhythm",
        "Coordinate movement of forces",
        "Execute Information Management procedures",
        "Conduct battle drills",
        "Maintain communications with HSS units",
        "Maintain common operational picture (COP)",
        "Conduct cross boundary coordination",
        "Synchronize staff section operations",
      ],
      requiredFootprint: ["Holding", "COC"],
    },
    {
      id: "MET 4",
      mctTask: "MCT 4.5.5",
      name: "Conduct Casualty Evacuation",
      pecls: [
        "Submit casualty evacuation request",
        "Receive guidance from HHQ",
        "Prepare the casualty",
        "Prepare documentation",
        "Conduct casualty turnover",
        "Evacuate casualty",
        "Receive casualty evacuation request",
        "Determine means of casualty movement",
        "Determine casualty destination facility",
        "Coordinate with DASC for air support",
        "Track casualty movement",
        "Conduct COC operations",
        "Establish medical watch",
        "Maintain battle rhythm",
        "Coordinate movement of forces",
      ],
      requiredFootprint: ["COC"],
    },
    {
      id: "MET 5",
      mctTask: "MCT 4.5.6",
      name: "Conduct Mass Casualty Operations",
      pecls: [
        "Determine the nature of incident",
        "Activate mass casualty plan",
        "Identify non-medical assets available to assist",
        "Conduct triage",
        "Provide emergency treatment, as indicated",
        "Determine patient transportation requirements",
        "Establish communication for evacuation of casualties",
        "Reassess triage categories assigned (NATO Casualty Categories)",
        "Evacuate casualties",
        "Provide command and control",
        "Establish medical watch",
        "Maintain battle rhythm",
        "Coordinate movement of forces",
        "Execute Information Management procedures",
        "Conduct battle drills",
        "Maintain communications with HSS units",
        "Maintain common operational picture (COP)",
      ],
      requiredFootprint: ["STP", "FRSS", "COC"],
    },
    {
      id: "MET 6",
      mctTask: "MCT 4.5.7",
      name: "Conduct and Provide Dental Services",
      pecls: [
        "Triage",
        "Perform History/physical examination",
        "Identify injury/illness",
        "Render standard of care",
        "Utilize ancillary services as needed",
        "Document care",
        "Disposition patient",
        "Perform emergency dental treatment",
        "Establish dental facility",
        "Identify lift requirements",
        "Move to location",
        "Employ tentage/equipment",
        "Establish communications",
        "Maintain capability for retrograde",
      ],
      requiredFootprint: ["Dental"],
    },
    {
      id: "MET 7",
      mctTask: "MCT 4.5.8",
      name: "Conduct Medical Regulating Services",
      pecls: [
        "Establish medical watch",
        "Maintain battle rhythm",
        "Coordinate movement of forces",
        "Execute Information Management procedures",
        "Conduct battle drills",
        "Maintain communications with HSS units",
        "Maintain common operational picture (COP)",
        "Conduct cross boundary coordination",
        "Synchronize staff section operations",
        "Receive casualty evacuation request",
        "Determine means of casualty movement",
        "Determine casualty destination facility",
        "Coordinate with DASC for air support",
        "Track casualty movement",
      ],
      requiredFootprint: ["COC"],
    },
  ];

  // Check if MET has all required footprint components selected
  const isMETFullySupported = (met: typeof MET_DATA[0]) => {
    return met.requiredFootprint.every(req => selectedFootprint.includes(req));
  };

  // Get missing footprint for a MET
  const getMissingFootprint = (met: typeof MET_DATA[0]) => {
    return met.requiredFootprint.filter(req => !selectedFootprint.includes(req));
  };

  // Toggle MET selection
  const toggleMET = (metId: string) => {
    setSelectedMETs(prev =>
      prev.includes(metId) ? prev.filter(m => m !== metId) : [...prev, metId]
    );
  };

  // Toggle footprint selection
  const toggleFootprint = (footprintId: string) => {
    setSelectedFootprint(prev =>
      prev.includes(footprintId) ? prev.filter(f => f !== footprintId) : [...prev, footprintId]
    );
  };

  // Select all METs
  const selectAllMETs = () => {
    setSelectedMETs(MET_DATA.map(m => m.id));
  };

  // Clear all METs
  const clearAllMETs = () => {
    setSelectedMETs([]);
  };

  // Select all footprint
  const selectAllFootprint = () => {
    setSelectedFootprint(FOOTPRINT.map(f => f.id));
  };

  // Clear all footprint
  const clearAllFootprint = () => {
    setSelectedFootprint([]);
  };

  // Update specialist count
  const updateSpecialist = (specialty: string, count: number) => {
    setSpecialists(prev => ({
      ...prev,
      [specialty]: Math.max(0, Math.min(5, count)),
    }));
  };

  // Load exerciseName from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('exerciseName');
    if (saved) setExerciseName(saved);
  }, []);

  // Persist exerciseName to localStorage on change
  useEffect(() => {
    localStorage.setItem('exerciseName', exerciseName);
  }, [exerciseName]);

  // Store duration in localStorage
  useEffect(() => {
    localStorage.setItem('exDuration', duration.toString());
  }, [duration]);

  // Generate exercise name
  const generateName = async () => {
    setIsGenerating(true);
    setNameError(null);
    try {
      const resp = await fetch(`${API_BASE}/generate-name`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ environment, region, threatLevel, supportedUnit, seed: Math.random() }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${resp.status}`);
      }
      const data = await resp.json();
      if (!data.name) throw new Error('No name returned');
      setExerciseName(data.name);
    } catch (e) {
      setNameError(e instanceof Error ? e.message : 'Failed to reach server');
    }
    setIsGenerating(false);
  };

  // Save configuration and proceed
  const saveAndProceed = () => {
    const config = {
      exercise_name: exerciseName,
      duration,
      supported_unit: supportedUnit,
      environment,
      threat_level: threatLevel,
      region,
      selected_mets: selectedMETs,
      selected_footprint: selectedFootprint,
      specialists,
    };
    localStorage.setItem('exerciseConfig', JSON.stringify(config));
    window.location.href = '/tactical';
  };

  // Shared style objects
  const sectionStyle: React.CSSProperties = {
    background: 'var(--surface-1)',
    border: '1px solid var(--border-1)',
    borderRadius: 'var(--radius-md)',
    padding: 20,
    marginBottom: 20,
  };

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontFamily: 'var(--font-body)',
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.10em',
    textTransform: 'uppercase',
    color: 'var(--ink-3)',
    marginBottom: 4,
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    background: 'var(--surface-2)',
    border: '1px solid var(--border-1)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--ink-1)',
    fontFamily: 'var(--font-body)',
    fontSize: 13,
    padding: '7px 10px',
    boxSizing: 'border-box',
  };

  const sectionHeadingStyle: React.CSSProperties = {
    fontFamily: 'var(--font-display)',
    fontWeight: 700,
    fontSize: 14,
    letterSpacing: '-0.01em',
    color: 'var(--ink-1)',
    margin: 0,
  };

  const dividerStyle: React.CSSProperties = {
    borderBottom: '1px solid var(--border-1)',
    marginBottom: 16,
    paddingBottom: 12,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  };

  const chipBtnStyle: React.CSSProperties = {
    fontFamily: 'var(--font-body)',
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    background: 'var(--surface-2)',
    color: 'var(--ink-2)',
    border: '1px solid var(--border-2)',
    borderRadius: 'var(--radius-sm)',
    padding: '4px 10px',
    cursor: 'pointer',
  };

  const stepperBtnStyle: React.CSSProperties = {
    width: 24,
    height: 24,
    borderRadius: 'var(--radius-sm)',
    background: 'var(--surface-2)',
    border: '1px solid var(--border-2)',
    color: 'var(--ink-2)',
    fontWeight: 700,
    fontSize: 14,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    lineHeight: 1,
  };

  return (
    <div
      data-theme="manual"
      style={{ maxWidth: 1200, margin: '0 auto', padding: '24px', background: 'var(--surface-0)', minHeight: '100vh' }}
    >
      {/* Header */}
      <header style={{ marginBottom: 28, borderBottom: '2px solid var(--border-2)', paddingBottom: 16 }}>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: 28,
          letterSpacing: '-0.01em',
          color: 'var(--ink-1)',
          margin: 0,
          textTransform: 'uppercase',
        }}>
          Role 2 Exercise Builder
        </h1>
        <p style={{
          fontFamily: 'var(--font-body)',
          fontWeight: 600,
          fontSize: 10,
          letterSpacing: '0.10em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          marginTop: 4,
          marginBottom: 0,
        }}>
          Medical Battalion Mission Essential Task Training Planner
        </p>
      </header>

      {/* Exercise Basics */}
      <section style={sectionStyle}>
        <div style={{ ...dividerStyle }}>
          <h2 style={sectionHeadingStyle}>Exercise Information</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Exercise Name */}
          <div className="lg:col-span-2">
            <label style={labelStyle}>Exercise Name</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={exerciseName}
                onChange={(e) => setExerciseName(e.target.value)}
                placeholder="e.g., Operation Pacific Sentinel"
                style={{ ...inputStyle, flex: 1 }}
              />
              <button
                onClick={generateName}
                disabled={isGenerating}
                style={{
                  background: nameError ? 'var(--signal-red)' : 'var(--accent)',
                  color: 'var(--accent-on)',
                  fontFamily: 'var(--font-body)',
                  fontWeight: 600,
                  fontSize: 10,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  border: 0,
                  borderRadius: 'var(--radius-md)',
                  padding: '0 14px',
                  cursor: isGenerating ? 'not-allowed' : 'pointer',
                  opacity: isGenerating ? 0.6 : 1,
                  whiteSpace: 'nowrap',
                }}
              >
                {isGenerating ? '...' : nameError ? 'Retry' : 'AI Gen'}
              </button>
            </div>
            {nameError && (
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--signal-red)', marginTop: 4, marginBottom: 0 }}>
                {nameError}
              </p>
            )}
          </div>

          {/* Duration */}
          <div>
            <label style={labelStyle}>Duration (Days)</label>
            <input
              type="number"
              value={duration}
              onChange={(e) => setDuration(Math.max(1, parseInt(e.target.value) || 1))}
              min="1"
              max="30"
              style={inputStyle}
            />
          </div>

          {/* Supported Unit */}
          <div>
            <label style={labelStyle}>Supported Unit</label>
            <select
              value={supportedUnit}
              onChange={(e) => setSupportedUnit(e.target.value)}
              style={inputStyle}
            >
              <option value="Division">Division</option>
              <option value="CLB">Combat Logistics Battalion (CLB)</option>
            </select>
          </div>
        </div>
      </section>

      {/* AOR Section */}
      <section style={sectionStyle}>
        <div style={dividerStyle}>
          <h2 style={sectionHeadingStyle}>Area of Responsibility (AOR)</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label style={labelStyle}>Environment</label>
            <select
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
              style={inputStyle}
            >
              {ENVIRONMENTS.map(env => (
                <option key={env} value={env}>{env}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={labelStyle}>Threat Level</label>
            <select
              value={threatLevel}
              onChange={(e) => setThreatLevel(e.target.value)}
              style={inputStyle}
            >
              {THREAT_LEVELS.map(threat => (
                <option key={threat} value={threat}>{threat}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={labelStyle}>Geographic Region</label>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              style={inputStyle}
            >
              {REGIONS.map(reg => (
                <option key={reg} value={reg}>{reg}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* Two Column Layout for METs and Footprint/Specialists */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
        {/* MET Selection */}
        <section style={{ ...sectionStyle, marginBottom: 0 }}>
          <div style={dividerStyle}>
            <h2 style={sectionHeadingStyle}>Mission Essential Tasks</h2>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={selectAllMETs} style={chipBtnStyle}>Select All</button>
              <button onClick={clearAllMETs} style={chipBtnStyle}>Clear</button>
            </div>
          </div>

          <div style={{ maxHeight: 500, overflowY: 'auto', paddingRight: 4, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {MET_DATA.map((met) => {
              const isSelected = selectedMETs.includes(met.id);
              const isFullySupported = isMETFullySupported(met);
              const missingFootprint = getMissingFootprint(met);
              const isExpanded = expandedMET === met.id;

              const metCardBorder = isSelected
                ? isFullySupported
                  ? '1px solid var(--signal-green)'
                  : '1px solid var(--signal-amber)'
                : '1px solid var(--border-1)';

              const metCardBg = isSelected
                ? isFullySupported
                  ? 'rgba(107,127,79,0.08)'
                  : 'rgba(201,154,46,0.08)'
                : 'var(--surface-2)';

              return (
                <div
                  key={met.id}
                  style={{
                    border: metCardBorder,
                    background: metCardBg,
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                  }}
                >
                  {/* MET Header */}
                  <div style={{ display: 'flex', alignItems: 'center', padding: '10px 12px' }}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleMET(met.id)}
                      style={{ width: 14, height: 14, marginRight: 10, flexShrink: 0, accentColor: 'var(--accent)' }}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 10,
                          background: 'var(--surface-3)',
                          color: 'var(--ink-2)',
                          padding: '2px 6px',
                          borderRadius: 'var(--radius-sm)',
                        }}>
                          {met.mctTask}
                        </span>
                        <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500, color: 'var(--ink-1)' }}>
                          {met.name}
                        </span>
                      </div>
                      {isSelected && !isFullySupported && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4 }}>
                          <svg style={{ width: 12, height: 12, color: 'var(--signal-amber)', flexShrink: 0 }} fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                          </svg>
                          <span style={{ fontFamily: 'var(--font-body)', fontSize: 10, color: 'var(--signal-amber)' }}>
                            Missing: {missingFootprint.join(', ')}
                          </span>
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => setExpandedMET(isExpanded ? null : met.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: 'var(--ink-3)' }}
                    >
                      <svg
                        style={{ width: 16, height: 16, transition: 'transform 0.2s', transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                  </div>

                  {/* PECLs Dropdown */}
                  {isExpanded && (
                    <div style={{ borderTop: '1px solid var(--border-1)', background: 'var(--surface-0)', padding: '10px 12px' }}>
                      <p style={{ ...labelStyle, marginBottom: 8 }}>
                        Performance Evaluation Checklist Items ({met.pecls.length})
                      </p>
                      <ul style={{ margin: 0, padding: 0, listStyle: 'none', maxHeight: 180, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {met.pecls.map((pecl, pIdx) => (
                          <li key={pIdx} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-3)', width: 18, flexShrink: 0 }}>{pIdx + 1}.</span>
                            <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--ink-2)' }}>{pecl}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-1)', fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-3)' }}>
            <span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>{selectedMETs.length}</span> of {MET_DATA.length} METs selected
          </div>
        </section>

        {/* Right Column: Footprint + Specialists */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Footprint Selection */}
          <section style={{ ...sectionStyle, marginBottom: 0 }}>
            <div style={dividerStyle}>
              <h2 style={sectionHeadingStyle}>Role 2 Footprint</h2>
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={selectAllFootprint} style={chipBtnStyle}>Select All</button>
                <button onClick={clearAllFootprint} style={chipBtnStyle}>Clear</button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {FOOTPRINT.map((component) => {
                const isSelected = selectedFootprint.includes(component.id);
                return (
                  <label
                    key={component.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '10px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: isSelected ? '1px solid var(--signal-green)' : '1px solid var(--border-1)',
                      background: isSelected ? 'rgba(107,127,79,0.08)' : 'var(--surface-2)',
                      cursor: 'pointer',
                      transition: 'border-color 0.15s, background 0.15s',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleFootprint(component.id)}
                      style={{ width: 14, height: 14, marginRight: 10, accentColor: 'var(--accent)', flexShrink: 0 }}
                    />
                    <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 500, color: 'var(--ink-1)' }}>
                      {component.name}
                    </span>
                  </label>
                );
              })}
            </div>

            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-1)', fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-3)' }}>
              <span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>{selectedFootprint.length}</span> of {FOOTPRINT.length} components selected
            </div>
          </section>

          {/* Specialist Staffing */}
          <section style={{ ...sectionStyle, marginBottom: 0 }}>
            <div style={dividerStyle}>
              <h2 style={sectionHeadingStyle}>Specialist Staffing</h2>
            </div>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--ink-3)', marginTop: 0, marginBottom: 14 }}>
              Set the number of each specialist available (0–5). This will inform case generation.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Nurses */}
              <div>
                <p style={{ ...labelStyle, marginBottom: 8 }}>Nursing</p>
                <div className="grid grid-cols-2 gap-2">
                  {["ERC Nurse", "ER Nurse", "ICU Nurse", "Med Surg Nurse"].map((specialty) => (
                    <div
                      key={specialty}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        background: 'var(--surface-2)',
                        border: '1px solid var(--border-1)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '8px 10px',
                      }}
                    >
                      <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-1)' }}>{specialty}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <button onClick={() => updateSpecialist(specialty, specialists[specialty] - 1)} style={stepperBtnStyle}>−</button>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-1)', width: 20, textAlign: 'center' }}>
                          {specialists[specialty]}
                        </span>
                        <button onClick={() => updateSpecialist(specialty, specialists[specialty] + 1)} style={stepperBtnStyle}>+</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Physicians */}
              <div>
                <p style={{ ...labelStyle, marginBottom: 8 }}>Physicians</p>
                <div className="grid grid-cols-2 gap-2">
                  {["Family Physician", "Emergency Medicine"].map((specialty) => (
                    <div
                      key={specialty}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        background: 'var(--surface-2)',
                        border: '1px solid var(--border-1)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '8px 10px',
                      }}
                    >
                      <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-1)' }}>{specialty}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <button onClick={() => updateSpecialist(specialty, specialists[specialty] - 1)} style={stepperBtnStyle}>−</button>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-1)', width: 20, textAlign: 'center' }}>
                          {specialists[specialty]}
                        </span>
                        <button onClick={() => updateSpecialist(specialty, specialists[specialty] + 1)} style={stepperBtnStyle}>+</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Surgeons */}
              <div>
                <p style={{ ...labelStyle, marginBottom: 8 }}>Surgical</p>
                <div className="grid grid-cols-2 gap-2">
                  {["General Surgery", "Orthopaedic Surgery", "Anesthesiology"].map((specialty) => (
                    <div
                      key={specialty}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        background: 'var(--surface-2)',
                        border: '1px solid var(--border-1)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '8px 10px',
                      }}
                    >
                      <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-1)' }}>{specialty}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <button onClick={() => updateSpecialist(specialty, specialists[specialty] - 1)} style={stepperBtnStyle}>−</button>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-1)', width: 20, textAlign: 'center' }}>
                          {specialists[specialty]}
                        </span>
                        <button onClick={() => updateSpecialist(specialty, specialists[specialty] + 1)} style={stepperBtnStyle}>+</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-1)', fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-3)' }}>
              Total specialists:&nbsp;
              <span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>
                {Object.values(specialists).reduce((a, b) => a + b, 0)}
              </span>
            </div>
          </section>
        </div>
      </div>

      {/* Summary & Navigation footer */}
      <section style={{
        background: 'var(--accent)',
        borderRadius: 'var(--radius-md)',
        padding: '20px 24px',
        marginBottom: 16,
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
            <div>
              <p style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent-on)', margin: 0 }}>
                Exercise Summary
              </p>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'rgba(22,24,20,0.75)', marginTop: 4, marginBottom: 0 }}>
                {exerciseName || 'Unnamed Exercise'} &bull; {duration} day{duration !== 1 ? 's' : ''} &bull; {supportedUnit} &bull; {environment} / {region}
              </p>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'rgba(22,24,20,0.65)', marginTop: 2, marginBottom: 0 }}>
                {selectedMETs.length} METs &bull; {selectedFootprint.length} Footprint Components &bull; {Object.values(specialists).reduce((a, b) => a + b, 0)} Specialists
              </p>
            </div>
            <button
              onClick={saveAndProceed}
              disabled={selectedMETs.length === 0}
              style={{
                background: selectedMETs.length === 0 ? 'rgba(22,24,20,0.20)' : 'var(--surface-0)',
                color: selectedMETs.length === 0 ? 'rgba(22,24,20,0.40)' : 'var(--ink-1)',
                fontFamily: 'var(--font-body)',
                fontWeight: 600,
                fontSize: 13,
                letterSpacing: '0.04em',
                border: 0,
                borderRadius: 'var(--radius-md)',
                padding: '12px 24px',
                cursor: selectedMETs.length === 0 ? 'not-allowed' : 'pointer',
                textTransform: 'uppercase',
                whiteSpace: 'nowrap',
              }}
            >
              Continue to Scenario Planning
            </button>
          </div>
        </div>
      </section>

      {/* History Link */}
      <div style={{ textAlign: 'center', marginTop: 8 }}>
        <a
          href="/history"
          style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-3)', textDecoration: 'underline' }}
        >
          View Past Exercises
        </a>
      </div>
    </div>
  );
}
