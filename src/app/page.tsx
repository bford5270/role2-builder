"use client";
import React, { useState, useEffect } from 'react';
import Link from 'next/link';

export default function SetupPage() {
  const [exerciseName, setExerciseName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [aor, setAor] = useState("Urban");
  const [unitType, setUnitType] = useState("Division");
  const [duration, setDuration] = useState(3);
  const [selectedMETs, setSelectedMETs] = useState<string[]>([]);
  const [selectedSpaces, setSelectedSpaces] = useState<string[]>([]);
  const [expandedMET, setExpandedMET] = useState<string | null>(null);
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null);

  const MET_DATA = [
    { id: 'MET 1', name: 'Provide Task-Organized Forces', events: [{ id: 'HSS-PLAN-7001', name: 'Conduct planning', pecls: ['Problem Framing', 'MCPP/R2P2', 'Timeline', 'Issue WARNO', 'Create Orders'] }] },
    { id: 'MET 2', name: 'Conduct Casualty Treatment', events: [
      { id: 'HSS-MBN-6001', name: 'Resuscitative Caps', pecls: ['FRSS', 'STP', 'Holding'] },
      { id: 'HSS-AID-5601', name: 'Aid Station HSS', pecls: ['Triage', 'Stabilize', 'Casualty Reports'] },
      { id: 'HSS-STP-5001', name: 'Resuscitative Facility', pecls: ['Lift ID', 'Tentage', 'Comms'] },
      { id: 'HSS-SVCS-3507', name: 'Medical Care', pecls: ['H&P', 'ID Injury', 'Render Care', 'Document'] }
    ]},
    { id: 'MET 3', name: 'Temporary Casualty Holding', events: [{ id: 'HSS-SVCS-3502', name: 'Temp Holding', pecls: ['Assess', 'Holding Capability', 'Accountability', 'Prepare Evac'] }] },
    { id: 'MET 4', name: 'Casualty Evacuation', events: [
      { id: 'HSS-SVCS-3401', name: 'CASEVAC', pecls: ['9-Line', 'Prepare Casualty', 'Turnover'] },
      { id: 'HSS-PET-4701', name: 'Patient Movement', pecls: ['Means/Destination', 'Track Movement'] }
    ]},
    { id: 'MET 5', name: 'MASCAL Operations', events: [{ id: 'HSS-SVCS-3701', name: 'Perform MASCAL', pecls: ['Activate Plan', 'Triage', 'Emergency Treatment', 'Evacuation'] }] },
    { id: 'MET 6', name: 'Dental Services', events: [{ id: 'HSS-DENT-3001', name: 'Provide Dental', pecls: ['Triage', 'Emergency Treatment', 'Ancillary Services'] }] },
    { id: 'MET 7', name: 'Medical Regulating', events: [{ id: 'HSS-OPS-6001', name: 'Command & Control', pecls: ['Medical Watch', 'COP', 'Information Management'] }] }
  ];

  const FOOTPRINT = ['STP', 'FRSS', 'Holding', 'Mortuary Affairs', 'Lab', 'Radiology', 'COC', 'Dental'];
  const SPECIALTIES = ['ERC nurse', 'Med Surg Nurse', 'ER Nurse', 'Critical Care Nurse', 'Family Physician', 'EM Doc', 'Anesthesiologist', 'Surgeon', 'Orthopedic Surgeon'];

  useEffect(() => { localStorage.setItem('exDuration', duration.toString()); }, [duration]);

  const generateName = async () => {
    setIsGenerating(true);
    try {
      const response = await fetch("https://role2-builder-production.up.railway.app/generate-name", { 
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aor, unitType, seed: Math.random() }) 
      });
      const data = await response.json();
      setExerciseName(data.name);
    } catch (e) { setExerciseName("Operation Obsidian Shield"); }
    setIsGenerating(false);
  };

  return (
    <div className="max-w-6xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <header className="mb-10 border-b-8 border-blue-900 pb-4">
        <h1 className="text-5xl font-black uppercase italic tracking-tighter text-blue-900">Role 2 Exercise Builder</h1>
        <p className="font-bold uppercase tracking-widest text-sm mt-2 text-slate-500">1st Med Bn Mission Planner</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8 text-xs font-bold">
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200">
          <label className="block text-[10px] text-slate-400 mb-2 uppercase tracking-widest">Duration (Days)</label>
          <input type="number" value={duration} onChange={(e) => setDuration(parseInt(e.target.value))} className="w-full border-2 border-slate-200 rounded p-2" min="1" />
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 col-span-2">
          <label className="block text-[10px] text-slate-400 mb-2 uppercase tracking-widest">Exercise Name</label>
          <div className="flex space-x-2">
            <input type="text" value={exerciseName} onChange={(e) => setExerciseName(e.target.value)} className="flex-1 border-2 border-slate-200 rounded p-2" />
            <button onClick={generateName} className="bg-blue-600 text-white px-4 rounded hover:bg-blue-700">{isGenerating ? "..." : "AI GEN"}</button>
          </div>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200"><label className="block text-[10px] text-slate-400 mb-2 uppercase">AOR</label>
          <select value={aor} onChange={(e) => setAor(e.target.value)} className="w-full border-2 border-slate-200 rounded p-2"><option>Urban</option><option>Jungle</option><option>Arctic</option><option>Desert</option></select>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200"><label className="block text-[10px] text-slate-400 mb-2 uppercase">Unit</label>
          <select value={unitType} onChange={(e) => setUnitType(e.target.value)} className="w-full border-2 border-slate-200 rounded p-2"><option>Division</option><option>CLB</option></select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
        <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
          <h2 className="text-xl font-black uppercase italic mb-6 border-b-2 pb-2">HSS T&R METL Hierarchy</h2>
          <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
            {MET_DATA.map(met => (
              <div key={met.id} className="border-2 border-slate-100 rounded-lg overflow-hidden">
                <div className="flex items-center p-3 bg-slate-50 hover:bg-blue-50 cursor-pointer">
                  <input type="checkbox" checked={selectedMETs.includes(met.id)} onChange={() => setSelectedMETs(selectedMETs.includes(met.id) ? selectedMETs.filter(id => id !== met.id) : [...selectedMETs, met.id])} className="h-5 w-5 mr-4" />
                  <div className="flex-1 font-black text-[10px] uppercase" onClick={() => setExpandedMET(expandedMET === met.id ? null : met.id)}>{met.id}: {met.name}</div>
                  <div className="font-black text-lg" onClick={() => setExpandedMET(expandedMET === met.id ? null : met.id)}>{expandedMET === met.id ? '▾' : '▸'}</div>
                </div>
                {expandedMET === met.id && (
                  <div className="p-4 bg-white border-t-2 border-slate-50 space-y-4">
                    {met.events.map(event => (
                      <div key={event.id} className="space-y-2">
                        <div className="flex justify-between items-center cursor-pointer p-2 bg-slate-100 rounded" onClick={() => setExpandedEvent(expandedEvent === event.id ? null : event.id)}>
                          <span className="text-[10px] font-bold text-blue-900 uppercase">{event.id}: {event.name}</span>
                          <span>{expandedEvent === event.id ? '▾' : '▸'}</span>
                        </div>
                        {expandedEvent === event.id && (
                          <div className="grid grid-cols-1 gap-1 pl-4 border-l-2 border-blue-200">
                            {event.pecls.map(pecl => <div key={pecl} className="text-[10px] text-slate-600 font-mono py-1">{pecl}</div>)}
                          </div>
                        )}
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
            <div className="flex justify-between items-center mb-6 border-b-2 pb-2"><h2 className="text-xl font-black uppercase italic">Role 2 Footprint</h2>
              <button onClick={() => setSelectedSpaces(selectedSpaces.length === FOOTPRINT.length ? [] : FOOTPRINT)} className="text-[10px] font-black bg-emerald-900 text-white px-3 py-1 rounded-full uppercase">Select All</button>
            </div>
            <div className="grid grid-cols-2 gap-3 text-[10px] font-bold uppercase">
              {FOOTPRINT.map(s => <label key={s} className="flex items-center space-x-2 p-2 bg-slate-50 rounded hover:bg-emerald-50 cursor-pointer border border-slate-100"><input type="checkbox" checked={selectedSpaces.includes(s)} onChange={() => setSelectedSpaces(selectedSpaces.includes(s) ? selectedSpaces.filter(x => x !== s) : [...selectedSpaces, s])} className="h-4 w-4" /> <span>{s}</span></label>)}
            </div>
          </section>
          <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
            <h2 className="text-xl font-black uppercase italic mb-6 border-b-2 pb-2">Specialty Evaluators</h2>
            <div className="space-y-2 max-h-80 overflow-y-auto pr-2">
              {SPECIALTIES.map(spec => <div key={spec} className="flex justify-between items-center bg-slate-50 p-3 rounded-lg border border-slate-200"><span className="text-[10px] font-black uppercase">{spec}</span><input type="number" defaultValue={0} className="w-16 text-center border-2 border-slate-300 rounded font-black text-blue-900" /></div>)}
            </div>
          </section>
        </div>
      </div>
      <Link href="/tactical"><button className="mt-12 w-full bg-slate-900 text-white font-black py-8 rounded-3xl shadow-2xl hover:bg-black transition text-3xl uppercase tracking-tighter border-b-[12px] border-slate-700">Set Casualty Flow →</button></Link>
    </div>
  );
}