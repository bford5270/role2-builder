"use client";
import React, { useState, useEffect } from 'react';
import Link from 'next/link';

export default function SetupPage() {
  const [exerciseName, setExerciseName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
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

  // Store duration in localStorage
  useEffect(() => {
    localStorage.setItem('exDuration', duration.toString());
  }, [duration]);

  // Generate exercise name
  const generateName = async () => {
    setIsGenerating(true);
    try {
      const resp = await fetch("https://role2-builder-production.up.railway.app/generate-name", {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          environment, 
          region, 
          threatLevel, 
          supportedUnit, 
          seed: Math.random() 
        }),
      });
      const data = await resp.json();
      setExerciseName(data.name);
    } catch (e) {
      // Fallback names based on region
      const fallbackNames: Record<string, string[]> = {
        "Indo-Pacific": ["Operation Pacific Sentinel", "Operation Iron Dragon", "Operation Typhoon Shield"],
        "CENTCOM": ["Operation Desert Forge", "Operation Sandstorm Guardian", "Operation Crimson Saber"],
        "EUCOM": ["Operation Baltic Thunder", "Operation Nordic Defender", "Operation Iron Resolve"],
        "AFRICOM": ["Operation Sahara Vigil", "Operation Lion's Shield", "Operation Obsidian Spear"],
        "SOUTHCOM": ["Operation Jungle Serpent", "Operation Condor Strike", "Operation Amazon Shield"],
        "NORTHCOM": ["Operation Arctic Defender", "Operation Polar Guardian", "Operation Northern Shield"],
      };
      const names = fallbackNames[region] || fallbackNames["Indo-Pacific"];
      setExerciseName(names[Math.floor(Math.random() * names.length)]);
    }
    setIsGenerating(false);
  };

  // Save configuration and proceed
  const saveAndProceed = () => {
    const config = {
      exerciseName,
      duration,
      supportedUnit,
      environment,
      threatLevel,
      region,
      selectedMETs,
      selectedFootprint,
      specialists,
    };
    localStorage.setItem('exerciseConfig', JSON.stringify(config));
    // Navigate to next page (scenario planning)
    window.location.href = '/tactical';
  };

  return (
    <div className="max-w-7xl mx-auto p-6 bg-slate-50 min-h-screen text-slate-900 font-sans">
      {/* Header */}
      <header className="mb-8 border-b-4 border-blue-900 pb-4">
        <h1 className="text-4xl font-black uppercase italic tracking-tight text-blue-900">
          Role 2 Exercise Builder
        </h1>
        <p className="font-semibold uppercase tracking-widest text-xs mt-1 text-slate-500">
          Medical Battalion Mission Essential Task Training Planner
        </p>
      </header>

      {/* Exercise Basics */}
      <section className="bg-white p-5 rounded-xl shadow-md border border-slate-200 mb-6">
        <h2 className="text-lg font-bold uppercase tracking-wide text-blue-900 mb-4 border-b pb-2">
          Exercise Information
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Exercise Name */}
          <div className="lg:col-span-2">
            <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
              Exercise Name
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={exerciseName}
                onChange={(e) => setExerciseName(e.target.value)}
                placeholder="e.g., Operation Pacific Sentinel"
                className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <button
                onClick={generateName}
                disabled={isGenerating}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white px-4 py-2 rounded-lg font-bold text-xs uppercase tracking-wide transition-colors"
              >
                {isGenerating ? "..." : "AI Gen"}
              </button>
            </div>
          </div>

          {/* Duration */}
          <div>
            <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
              Duration (Days)
            </label>
            <input
              type="number"
              value={duration}
              onChange={(e) => setDuration(Math.max(1, parseInt(e.target.value) || 1))}
              min="1"
              max="30"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Supported Unit */}
          <div>
            <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
              Supported Unit
            </label>
            <select
              value={supportedUnit}
              onChange={(e) => setSupportedUnit(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
            >
              <option value="Division">Division</option>
              <option value="CLB">Combat Logistics Battalion (CLB)</option>
            </select>
          </div>
        </div>
      </section>

      {/* AOR Section */}
      <section className="bg-white p-5 rounded-xl shadow-md border border-slate-200 mb-6">
        <h2 className="text-lg font-bold uppercase tracking-wide text-blue-900 mb-4 border-b pb-2">
          Area of Responsibility (AOR)
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Environment */}
          <div>
            <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
              Environment
            </label>
            <select
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
            >
              {ENVIRONMENTS.map(env => (
                <option key={env} value={env}>{env}</option>
              ))}
            </select>
          </div>

          {/* Threat Level */}
          <div>
            <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
              Threat Level
            </label>
            <select
              value={threatLevel}
              onChange={(e) => setThreatLevel(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
            >
              {THREAT_LEVELS.map(threat => (
                <option key={threat} value={threat}>{threat}</option>
              ))}
            </select>
          </div>

          {/* Geographic Region */}
          <div>
            <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
              Geographic Region
            </label>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
            >
              {REGIONS.map(reg => (
                <option key={reg} value={reg}>{reg}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* Two Column Layout for METs and Footprint/Specialists */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* MET Selection */}
        <section className="bg-white p-5 rounded-xl shadow-md border border-slate-200">
          <div className="flex justify-between items-center mb-4 border-b pb-2">
            <h2 className="text-lg font-bold uppercase tracking-wide text-blue-900">
              Mission Essential Tasks
            </h2>
            <div className="flex gap-2">
              <button
                onClick={selectAllMETs}
                className="text-xs font-bold uppercase bg-blue-100 hover:bg-blue-200 text-blue-700 px-3 py-1 rounded transition-colors"
              >
                Select All
              </button>
              <button
                onClick={clearAllMETs}
                className="text-xs font-bold uppercase bg-slate-100 hover:bg-slate-200 text-slate-600 px-3 py-1 rounded transition-colors"
              >
                Clear
              </button>
            </div>
          </div>

          <div className="space-y-2 max-h-[500px] overflow-y-auto pr-2">
            {MET_DATA.map((met) => {
              const isSelected = selectedMETs.includes(met.id);
              const isFullySupported = isMETFullySupported(met);
              const missingFootprint = getMissingFootprint(met);
              const isExpanded = expandedMET === met.id;

              return (
                <div
                  key={met.id}
                  className={`border rounded-lg overflow-hidden transition-all ${
                    isSelected
                      ? isFullySupported
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-amber-500 bg-amber-50'
                      : 'border-slate-200 bg-white'
                  }`}
                >
                  {/* MET Header */}
                  <div className="flex items-center p-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleMET(met.id)}
                      className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 mr-3"
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono bg-slate-200 px-2 py-0.5 rounded">
                          {met.mctTask}
                        </span>
                        <span className="font-semibold text-sm">{met.name}</span>
                      </div>
                      {isSelected && !isFullySupported && (
                        <div className="text-xs text-amber-700 mt-1 flex items-center gap-1">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                          </svg>
                          Missing: {missingFootprint.join(', ')}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => setExpandedMET(isExpanded ? null : met.id)}
                      className="text-slate-400 hover:text-slate-600 p-1"
                    >
                      <svg
                        className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
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
                    <div className="border-t border-slate-200 bg-slate-50 p-3">
                      <p className="text-xs font-bold uppercase text-slate-500 mb-2">
                        Performance Evaluation Checklist Items ({met.pecls.length})
                      </p>
                      <ul className="text-xs text-slate-600 space-y-1 max-h-48 overflow-y-auto">
                        {met.pecls.map((pecl, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="text-slate-400 font-mono w-4">{idx + 1}.</span>
                            <span>{pecl}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-3 pt-3 border-t text-sm text-slate-500">
            <span className="font-semibold">{selectedMETs.length}</span> of {MET_DATA.length} METs selected
          </div>
        </section>

        {/* Right Column: Footprint + Specialists */}
        <div className="space-y-6">
          {/* Footprint Selection */}
          <section className="bg-white p-5 rounded-xl shadow-md border border-slate-200">
            <div className="flex justify-between items-center mb-4 border-b pb-2">
              <h2 className="text-lg font-bold uppercase tracking-wide text-blue-900">
                Role 2 Footprint
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={selectAllFootprint}
                  className="text-xs font-bold uppercase bg-blue-100 hover:bg-blue-200 text-blue-700 px-3 py-1 rounded transition-colors"
                >
                  Select All
                </button>
                <button
                  onClick={clearAllFootprint}
                  className="text-xs font-bold uppercase bg-slate-100 hover:bg-slate-200 text-slate-600 px-3 py-1 rounded transition-colors"
                >
                  Clear
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {FOOTPRINT.map((component) => {
                const isSelected = selectedFootprint.includes(component.id);
                return (
                  <label
                    key={component.id}
                    className={`flex items-center p-3 rounded-lg border cursor-pointer transition-all ${
                      isSelected
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-slate-200 bg-white hover:bg-slate-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleFootprint(component.id)}
                      className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 mr-3"
                    />
                    <span className="text-sm font-medium">{component.name}</span>
                  </label>
                );
              })}
            </div>

            <div className="mt-3 pt-3 border-t text-sm text-slate-500">
              <span className="font-semibold">{selectedFootprint.length}</span> of {FOOTPRINT.length} components selected
            </div>
          </section>

          {/* Specialist Staffing */}
          <section className="bg-white p-5 rounded-xl shadow-md border border-slate-200">
            <h2 className="text-lg font-bold uppercase tracking-wide text-blue-900 mb-4 border-b pb-2">
              Specialist Staffing
            </h2>
            <p className="text-xs text-slate-500 mb-4">
              Set the number of each specialist available (0-5). This will inform case generation.
            </p>

            <div className="space-y-3">
              {/* Nurses */}
              <div>
                <p className="text-xs font-bold uppercase text-slate-400 mb-2">Nursing</p>
                <div className="grid grid-cols-2 gap-2">
                  {["ERC Nurse", "ER Nurse", "ICU Nurse", "Med Surg Nurse"].map((specialty) => (
                    <div
                      key={specialty}
                      className="flex items-center justify-between bg-slate-50 rounded-lg p-2 border border-slate-200"
                    >
                      <span className="text-sm font-medium">{specialty}</span>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => updateSpecialist(specialty, specialists[specialty] - 1)}
                          className="w-6 h-6 rounded bg-slate-200 hover:bg-slate-300 text-slate-600 font-bold text-sm"
                        >
                          −
                        </button>
                        <span className="w-6 text-center font-mono text-sm">
                          {specialists[specialty]}
                        </span>
                        <button
                          onClick={() => updateSpecialist(specialty, specialists[specialty] + 1)}
                          className="w-6 h-6 rounded bg-slate-200 hover:bg-slate-300 text-slate-600 font-bold text-sm"
                        >
                          +
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Physicians */}
              <div>
                <p className="text-xs font-bold uppercase text-slate-400 mb-2">Physicians</p>
                <div className="grid grid-cols-2 gap-2">
                  {["Family Physician", "Emergency Medicine"].map((specialty) => (
                    <div
                      key={specialty}
                      className="flex items-center justify-between bg-slate-50 rounded-lg p-2 border border-slate-200"
                    >
                      <span className="text-sm font-medium">{specialty}</span>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => updateSpecialist(specialty, specialists[specialty] - 1)}
                          className="w-6 h-6 rounded bg-slate-200 hover:bg-slate-300 text-slate-600 font-bold text-sm"
                        >
                          −
                        </button>
                        <span className="w-6 text-center font-mono text-sm">
                          {specialists[specialty]}
                        </span>
                        <button
                          onClick={() => updateSpecialist(specialty, specialists[specialty] + 1)}
                          className="w-6 h-6 rounded bg-slate-200 hover:bg-slate-300 text-slate-600 font-bold text-sm"
                        >
                          +
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Surgeons */}
              <div>
                <p className="text-xs font-bold uppercase text-slate-400 mb-2">Surgical</p>
                <div className="grid grid-cols-2 gap-2">
                  {["General Surgery", "Orthopaedic Surgery", "Anesthesiology"].map((specialty) => (
                    <div
                      key={specialty}
                      className="flex items-center justify-between bg-slate-50 rounded-lg p-2 border border-slate-200"
                    >
                      <span className="text-sm font-medium">{specialty}</span>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => updateSpecialist(specialty, specialists[specialty] - 1)}
                          className="w-6 h-6 rounded bg-slate-200 hover:bg-slate-300 text-slate-600 font-bold text-sm"
                        >
                          −
                        </button>
                        <span className="w-6 text-center font-mono text-sm">
                          {specialists[specialty]}
                        </span>
                        <button
                          onClick={() => updateSpecialist(specialty, specialists[specialty] + 1)}
                          className="w-6 h-6 rounded bg-slate-200 hover:bg-slate-300 text-slate-600 font-bold text-sm"
                        >
                          +
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-3 pt-3 border-t text-sm text-slate-500">
              Total specialists: <span className="font-semibold">
                {Object.values(specialists).reduce((a, b) => a + b, 0)}
              </span>
            </div>
          </section>
        </div>
      </div>

      {/* Summary & Navigation */}
      <section className="bg-blue-900 text-white p-5 rounded-xl shadow-md">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h3 className="font-bold uppercase tracking-wide">Exercise Summary</h3>
            <p className="text-blue-200 text-sm mt-1">
              {exerciseName || "Unnamed Exercise"} • {duration} day{duration !== 1 ? 's' : ''} • {supportedUnit} • {environment} / {region}
            </p>
            <p className="text-blue-200 text-sm">
              {selectedMETs.length} METs • {selectedFootprint.length} Footprint Components • {Object.values(specialists).reduce((a, b) => a + b, 0)} Specialists
            </p>
          </div>
          <button
            onClick={saveAndProceed}
            disabled={selectedMETs.length === 0}
            className="bg-white hover:bg-blue-50 disabled:bg-slate-300 disabled:text-slate-500 text-blue-900 px-6 py-3 rounded-lg font-bold uppercase tracking-wide transition-colors"
          >
            Continue to Scenario Planning →
          </button>
        </div>
      </section>
    </div>
  );
}
