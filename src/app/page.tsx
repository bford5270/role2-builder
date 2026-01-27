"use client";
import React, { useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronRight } from 'lucide-react';

export default function SetupPage() {
  const [exerciseName, setExerciseName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [aor, setAor] = useState("Urban");
  const [unitType, setUnitType] = useState("Division");
  const [duration, setDuration] = useState(3);
  const [selectedMETs, setSelectedMETs] = useState<string[]>([]);
  const [expandedMET, setExpandedMET] = useState<string | null>(null);

  // FULL DATA FROM NAVMC 3500.84A
  const MET_DATA = [
    { id: 'MET 1', name: 'Provide Task-Organized Forces', events: ['HSS-PLAN-7001', 'HSS-PLAN-6001'] },
    { id: 'MET 2', name: 'Conduct Casualty Treatment', events: ['HSS-MBN-6001', 'HSS-AID-5601', 'HSS-STP-5001', 'HSS-FRSS-4001', 'HSS-PET-4701', 'HSS-SVCS-3701', 'HSS-SVCS-3501', 'HSS-SVCS-3502', 'HSS-SVCS-3507', 'HSS-SVCS-3401', 'HSS-DENT-3401', 'HSS-DENT-3001', 'HSS-DENT-3002'] },
    { id: 'MET 3', name: 'Conduct Temporary Casualty Holding', events: ['HSS-OPS-7001', 'HSS-MBN-6001', 'HSS-STP-5001', 'HSS-AID-5601', 'HSS-DENT-3001', 'HSS-DENT-3002', 'HSS-SVCS-3401', 'HSS-SVCS-3501', 'HSS-SVCS-3502', 'HSS-SVCS-3507', 'HSS-SVCS-3701'] },
    { id: 'MET 4', name: 'Conduct Casualty Evacuation', events: ['HSS-OPS-7001', 'HSS-PLAN-7001', 'HSS-PLAN-6001', 'HSS-OPS-6001', 'HSS-MBN-6001', 'HSS-AID-5601', 'HSS-STP-5001', 'HSS-PET-4701', 'HSS-FRSS-4001', 'HSS-SVCS-3701', 'HSS-SVCS-3502', 'HSS-SVCS-3507', 'HSS-SVCS-3401', 'HSS-DENT-3001', 'HSS-DENT-3002'] },
    { id: 'MET 5', name: 'Conduct Mass Casualty Operations', events: ['HSS-OPS-7001', 'HSS-PLAN-7001', 'HSS-OPS-6001', 'HSS-PLAN-6001', 'HSS-MBN-6001', 'HSS-AID-5601', 'HSS-STP-5001', 'HSS-SVCS-3701', 'HSS-SVCS-3501', 'HSS-SVCS-3507', 'HSS-SVCS-3401', 'HSS-DENT-3001', 'HSS-DENT-3002'] },
    { id: 'MET 6', name: 'Conduct and Provide Dental Services', events: ['HSS-OPS-7001', 'HSS-PLAN-7001', 'HSS-MBN-6001', 'HSS-PLAN-6001', 'HSS-AID-5601', 'HSS-STP-5001', 'HSS-SVCS-3701', 'HSS-SVCS-3501', 'HSS-SVCS-3502', 'HSS-SVCS-3507', 'HSS-DENT-3001', 'HSS-DENT-3002'] },
    { id: 'MET 7', name: 'Conduct Medical Regulating Services', events: ['HSS-OPS-7001', 'HSS-MBN-6001', 'HSS-OPS-6001', 'HSS-AID-5601', 'HSS-STP-5001', 'HSS-PET-4701', 'HSS-SVCS-3701', 'HSS-SVCS-3501', 'HSS-SVCS-3502', 'HSS-SVCS-3507', 'HSS-DENT-3001', 'HSS-DENT-3002'] },
  ];

  const ROLE_2_FOOTPRINT = ['STP', 'FRSS', 'Holding', 'Mortuary Affairs', 'Lab', 'Radiology', 'COC', 'Dental'];
  const SPECIALTIES = ['ERC nurse', 'Med Surg Nurse', 'ER Nurse', 'Critical Care Nurse', 'Family Physician', 'EM Doc', 'Anesthesiologist', 'Surgeon', 'Orthopedic Surgeon'];

  const handleSelectAllMETs = () => {
    if (selectedMETs.length === MET_DATA.length) setSelectedMETs([]);
    else setSelectedMETs(MET_DATA.map(m => m.id));
  };

  const generateName = async () => {
    setIsGenerating(true);
    try {
      const response = await fetch("https://role2-builder-production.up.railway.app/generate-name", { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aor, unitType, seed: Math.random() }) 
      });
      const data = await response.json();
      setExerciseName(data.name);
    } catch (e) { setExerciseName("Operation Iron Medic"); }
    setIsGenerating(false);
  };

  return (
    <div className="max-w-6xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <header className="mb-10 border-b-8 border-blue-900 pb-4">
        <h1 className="text-5xl font-black uppercase italic tracking-tighter">Role 2 Exercise Builder</h1>
        <p className="text-blue-700 font-bold uppercase tracking-widest text-sm mt-2">1st Med Bn Mission Planner</p>
      </header>

      {/* MISSION CONTEXT */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200">
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Primary AOR</label>
          <select value={aor} onChange={(e) => setAor(e.target.value)} className="w-full border-2 border-slate-200 rounded p-2 font-bold bg-slate-50">
            <option>Urban</option><option>Jungle</option><option>Arctic</option><option>Desert</option>
          </select>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200">
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Supported Unit</label>
          <select value={unitType} onChange={(e) => setUnitType(e.target.value)} className="w-full border-2 border-slate-200 rounded p-2 font-bold bg-slate-50">
            <option>Division</option><option>CLB</option>
          </select>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 col-span-2">
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Exercise Name</label>
          <div className="flex space-x-2">
            <input type="text" value={exerciseName} onChange={(e) => setExerciseName(e.target.value)} className="flex-1 border-2 border-slate-300 rounded p-2 font-bold" />
            <button onClick={generateName} className="bg-blue-600 text-white px-4 rounded font-black text-xs hover:bg-blue-700 transition active:scale-95">{isGenerating ? "..." : "AI GEN"}</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
        {/* T&R METL SECTION WITH ALL 7 METS */}
        <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
          <div className="flex justify-between items-center mb-6 border-b-2 pb-2">
            <h2 className="text-xl font-black uppercase italic text-slate-800">HSS T&R METL</h2>
            <button onClick={handleSelectAllMETs} className="text-[10px] font-black bg-slate-900 text-white px-3 py-1 rounded-full uppercase">Select All METs</button>
          </div>
          <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
            {MET_DATA.map(met => (
              <div key={met.id} className="border-2 border-slate-100 rounded-lg overflow-hidden">
                <div className="flex items-center p-3 bg-slate-50 hover:bg-blue-50 transition cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={selectedMETs.includes(met.id)}
                    onChange={() => {
                      if (selectedMETs.includes(met.id)) setSelectedMETs(selectedMETs.filter(id => id !== met.id));
                      else setSelectedMETs([...selectedMETs, met.id]);
                    }}
                    className="h-5 w-5 mr-4 cursor-pointer" 
                  />
                  <div className="flex-1 font-bold text-[10px] uppercase leading-tight" onClick={() => setExpandedMET(expandedMET === met.id ? null : met.id)}>
                    {met.id}: {met.name}
                  </div>
                  <div onClick={() => setExpandedMET(expandedMET === met.id ? null : met.id)}>
                    {expandedMET === met.id ? <ChevronDown size={18}/> : <ChevronRight size={18}/>}
                  </div>
                </div>
                {expandedMET === met.id && (
                  <div className="p-4 bg-white border-t-2 border-slate-50 space-y-2">
                    <p className="text-[9px] font-black text-blue-800 uppercase italic">PECLs & Supporting Events[cite: 7, 9, 11, 13, 15, 17, 19]:</p>
                    {met.events.map(event => (
                      <div key={event} className="text-[10px] text-slate-600 border-l-2 border-blue-200 pl-3 font-mono leading-none py-1">
                        {event}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        <div className="space-y-8">
          <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
            <h2 className="text-xl font-black uppercase italic mb-4">Role 2 Footprint</h2>
            <div className="grid grid-cols-2 gap-2">
              {ROLE_2_FOOTPRINT.map(s => (
                <label key={s} className="flex items-center space-x-2 p-2 bg-slate-50 rounded text-[10px] font-bold uppercase cursor-pointer hover:bg-emerald-50">
                  <input type="checkbox" className="h-4 w-4" /> <span>{s}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
            <h2 className="text-xl font-black uppercase italic mb-4">Specialty Evaluators</h2>
            <div className="space-y-2 max-h-60 overflow-y-auto pr-2">
              {SPECIALTIES.map(spec => (
                <div key={spec} className="flex justify-between items-center bg-slate-50 p-2 rounded border">
                  <span className="text-[10px] font-black uppercase text-slate-700">{spec}</span>
                  <input type="number" defaultValue={0} className="w-12 text-center border-2 border-slate-200 rounded font-black text-blue-900" />
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>

      <Link href="/tactical">
        <button className="mt-12 w-full bg-slate-900 text-white font-black py-8 rounded-3xl shadow-2xl hover:bg-black transition text-3xl uppercase tracking-tighter border-b-[12px] border-slate-700">
          Set Casualty Flow →
        </button>
      </Link>
    </div>
  );
}