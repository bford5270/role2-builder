"use client";
import React, { useState } from 'react';
import Link from 'next/link';

export default function SetupPage() {
  const [exerciseName, setExerciseName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [aor, setAor] = useState("Urban");
  const [unitType, setUnitType] = useState("Division (Infantry/Artillery)");
  const [duration, setDuration] = useState(3);

  // User-Defined Manifests
  const MET_PECL_LIST = [
    'MET 1: Provide Task-Organized Forces', 'MET 2: Conduct Casualty Treatment', 
    'MET 3: Conduct Temp Casualty Holding', 'MET 4: Conduct CASEVAC', 
    'MET 5: Conduct MASCAL Ops', 'PECL: Triage & Disposition', 'PECL: Surgical Intervention',
    'PECL: Damage Control Resuscitation', 'PECL: En Route Care'
  ];

  const ROLE_2_FOOTPRINT = [
    'STP', 'FRSS', 'Holding', 'Mortuary Affairs', 'Lab', 'Radiology', 'COC', 'Dental'
  ];

  const SPECIALTY_EVALS = [
    'ERC nurse', 'Med Surg Nurse', 'ER Nurse', 'Critical Care Nurse', 
    'Family Physician', 'EM Doc', 'Anesthesiologist', 'Surgeon', 'Orthopedic Surgeon'
  ];

  // Selection States
  const [selectedMETs, setSelectedMETs] = useState<string[]>([]);
  const [selectedSpaces, setSelectedSpaces] = useState<string[]>([]);

  const toggleAll = (list: string[], current: string[], setter: any) => {
    if (current.length === list.length) setter([]);
    else setter(list);
  };

  const generateName = async () => {
    setIsGenerating(true);
    try {
      const response = await fetch("https://role2-builder-production.up.railway.app/generate-name", { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aor, unitType })
      });
      const data = await response.json();
      setExerciseName(data.name);
    } catch (e) { setExerciseName("Operation Crimson Scalpel"); }
    setIsGenerating(false);
  };

  return (
    <div className="max-w-6xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <header className="mb-10 border-b-8 border-blue-900 pb-4">
        <h1 className="text-5xl font-black uppercase italic tracking-tighter">Role 2 Exercise Builder</h1>
        <p className="text-blue-700 font-bold uppercase tracking-widest text-sm mt-2">1st Med Bn | CMO Mission Planner</p>
      </header>

      {/* MISSION CONTEXT */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm">
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Primary AOR</label>
          <select value={aor} onChange={(e) => setAor(e.target.value)} className="w-full border-2 border-slate-200 rounded p-2 font-bold bg-slate-50">
            <option>Urban</option><option>Jungle</option><option>Arctic</option><option>Desert</option>
          </select>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm">
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Supported Unit</label>
          <select value={unitType} onChange={(e) => setUnitType(e.target.value)} className="w-full border-2 border-slate-200 rounded p-2 font-bold bg-slate-50">
            <option>Division (Infantry/Artillery)</option>
            <option>Combat Logistics Battalion (CLB)</option>
          </select>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm">
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Duration (Days)</label>
          <input type="number" value={duration} onChange={(e) => setDuration(parseInt(e.target.value))} className="w-full border-2 border-slate-200 rounded p-2 font-bold" />
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm">
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Exercise Name</label>
          <div className="flex space-x-2">
            <input type="text" value={exerciseName} onChange={(e) => setExerciseName(e.target.value)} className="flex-1 border-2 border-slate-300 rounded p-2 font-bold text-sm" placeholder="EX: STEEL KNIGHT" />
            <button onClick={generateName} className="bg-blue-600 text-white px-3 rounded font-black text-[10px] hover:bg-blue-700">{isGenerating ? "..." : "AI GEN"}</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
        <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
          <div className="flex justify-between items-center mb-6 border-b-2 border-slate-100 pb-2">
            <h2 className="text-xl font-black uppercase italic text-slate-800">T&R METs & PECLs</h2>
            <button onClick={() => toggleAll(MET_PECL_LIST, selectedMETs, setSelectedMETs)} className="text-[10px] font-black bg-blue-900 text-white px-3 py-1 rounded-full uppercase">Select All</button>
          </div>
          <div className="grid grid-cols-1 gap-2 max-h-96 overflow-y-auto pr-2">
            {MET_PECL_LIST.map(item => (
              <label key={item} className="flex items-center space-x-3 p-3 bg-slate-50 rounded-lg hover:bg-blue-50 cursor-pointer transition border border-transparent hover:border-blue-200">
                <input type="checkbox" checked={selectedMETs.includes(item)} onChange={() => {
                  if (selectedMETs.includes(item)) setSelectedMETs(selectedMETs.filter(i => i !== item));
                  else setSelectedMETs([...selectedMETs, item]);
                }} className="h-5 w-5 rounded border-slate-400" />
                <span className="text-xs font-bold text-slate-700 uppercase">{item}</span>
              </label>
            ))}
          </div>
        </section>

        <div className="space-y-10">
          {/* ROLE 2 FOOTPRINT */}
          <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
            <div className="flex justify-between items-center mb-6 border-b-2 border-slate-100 pb-2">
              <h2 className="text-xl font-black uppercase italic text-slate-800">Role 2 Footprint</h2>
              <button onClick={() => toggleAll(ROLE_2_FOOTPRINT, selectedSpaces, setSelectedSpaces)} className="text-[10px] font-black bg-emerald-900 text-white px-3 py-1 rounded-full uppercase">Select All</button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {ROLE_2_FOOTPRINT.map(space => (
                <label key={space} className="flex items-center space-x-3 p-2 bg-slate-50 rounded hover:bg-emerald-50 cursor-pointer transition border border-slate-100">
                  <input type="checkbox" checked={selectedSpaces.includes(space)} onChange={() => {
                    if (selectedSpaces.includes(space)) setSelectedSpaces(selectedSpaces.filter(s => s !== space));
                    else setSelectedSpaces([...selectedSpaces, space]);
                  }} className="h-4 w-4" />
                  <span className="text-[10px] font-black text-slate-600 uppercase">{space}</span>
                </label>
              ))}
            </div>
          </section>

          {/* SPECIALTY EVALUATORS */}
          <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
            <h2 className="text-xl font-black uppercase italic text-slate-800 mb-6 border-b-2 border-slate-100 pb-2">Specialty Evaluators</h2>
            <div className="grid grid-cols-1 gap-4 max-h-80 overflow-y-auto pr-2">
              {SPECIALTY_EVALS.map(spec => (
                <div key={spec} className="flex justify-between items-center bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <span className="text-[10px] font-black uppercase text-slate-700">{spec}</span>
                  <input type="number" defaultValue={0} min={0} className="w-16 text-center border-2 border-slate-300 rounded font-black text-blue-900" />
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>

      <Link href="/tactical">
        <button className="mt-12 w-full bg-slate-900 text-white font-black py-8 rounded-3xl shadow-2xl hover:bg-black transition text-3xl uppercase tracking-tighter border-b-[12px] border-slate-700 active:border-b-0 active:translate-y-2">
          Set Casualty Flow →
        </button>
      </Link>
    </div>
  );
}