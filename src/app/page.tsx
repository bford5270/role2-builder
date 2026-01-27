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
    { id: 'MET 1', name: 'Provide Task-Organized Forces', events: [{ id: 'HSS-PLAN-7001', name: 'Conduct planning', pecls: ['Problem Framing', 'MCPP/R2P2', 'Timeline', 'Issue WARNO'] }, { id: 'HSS-PLAN-6001', name: 'Conduct planning', pecls: ['Problem Framing', 'MCPP/R2P2', 'Timeline', 'Issue WARNO'] }] },
    { 
      id: 'MET 2', 
      name: 'Conduct Casualty Treatment', 
      events: [
        { id: 'HSS-MBN-6001', name: 'Establish resuscitative/surgical capabilities', pecls: ['Provide FRSS', 'Provide STP', 'Provide temp holding'] },
        { id: 'HSS-AID-5601', name: 'Provide Aid Station Health Services Support', pecls: ['Triage', 'Treat', 'Stabilize', 'Casualty Reports', 'DNBI'] },
        { id: 'HSS-STP-5001', name: 'Establish a resuscitative facility', pecls: ['ID lift', 'Move', 'Employ tentage', 'Establish comms'] },
        { id: 'HSS-PET-4701', name: 'Coordinate patient movement', pecls: ['Receive request', 'Determine means', 'Track movement'] },
        { id: 'HSS-SVCS-3701', name: 'Perform mass casualty', pecls: ['Activate plan', 'Conduct triage', 'Emergency treatment'] },
        { id: 'HSS-SVCS-3501', name: 'Receive casualties', pecls: ['Triage', 'Check-in', 'Security screening'] },
        { id: 'HSS-SVCS-3502', name: 'Conduct temporary casualty holding', pecls: ['Assess', 'Provide holding', 'Accountability'] },
        { id: 'HSS-SVCS-3507', name: 'Perform medical care', pecls: ['H&P', 'ID injury', 'Render care', 'Document'] },
        { id: 'HSS-SVCS-3401', name: 'Conduct casualty evacuation', pecls: ['Submit 9-line', 'Prepare casualty', 'Turnover'] },
        { id: 'HSS-DENT-3401', name: 'Establish a dental facility', pecls: ['Site prep', 'Tentage', 'Dental equipment setup'] },
        { id: 'HSS-DENT-3001', name: 'Provide dental services', pecls: ['Routine care', 'Ancillary services', 'Documentation'] },
        { id: 'HSS-DENT-3002', name: 'Perform emergency dental treatment', pecls: ['Emergency Triage', 'Pain management', 'Disposition'] }
      ] 
    },
    { id: 'MET 3', name: 'Conduct Temporary Casualty Holding', events: [{ id: 'HSS-SVCS-3502', name: 'Conduct temp holding', pecls: ['Assess', 'Hold', 'Document'] }] },
    { id: 'MET 4', name: 'Conduct Casualty Evacuation', events: [{ id: 'HSS-SVCS-3401', name: 'Conduct CASEVAC', pecls: ['9-line', 'Turnover'] }, { id: 'HSS-PET-4701', name: 'Patient Movement', pecls: ['Coordinate Air', 'Track'] }] },
    { id: 'MET 5', name: 'Conduct Mass Casualty Operations', events: [{ id: 'HSS-SVCS-3701', name: 'Perform MASCAL', pecls: ['Triage', 'Emergency treatment'] }] },
    { id: 'MET 6', name: 'Conduct and Provide Dental Services', events: [{ id: 'HSS-DENT-3001', name: 'Dental Services', pecls: ['Triage', 'Treatment'] }] },
    { id: 'MET 7', name: 'Conduct Medical Regulating Services', events: [{ id: 'HSS-OPS-6001', name: 'Command and Control', pecls: ['Medical Watch', 'Battle Rhythm'] }] }
  ];

  const FOOTPRINT = ['STP', 'FRSS', 'Holding', 'Mortuary Affairs', 'Lab', 'Radiology', 'COC', 'Dental'];
  const SPECIALTIES = ['ERC nurse', 'Med Surg Nurse', 'ER Nurse', 'Critical Care Nurse', 'Family Physician', 'EM Doc', 'Anesthesiologist', 'Surgeon', 'Orthopedic Surgeon'];

  useEffect(() => { localStorage.setItem('exDuration', duration.toString()); }, [duration]);

  const generateName = async () => {
    setIsGenerating(true);
    try {
      const resp = await fetch("https://role2-builder-production.up.railway.app/generate-name", { 
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aor, unitType, seed: Math.random() }) 
      });
      const data = await resp.json(); setExerciseName(data.name);
    } catch (e) { setExerciseName("Operation Obsidian Shield"); }
    setIsGenerating(false);
  };

  return (
    <div className="max-w-6xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <header className="mb-10 border-b-8 border-blue-900 pb-4">
        <h1 className="text-5xl font-black uppercase italic tracking-tighter text-blue-900">Role 2 Exercise Builder</h1>
        <p className="font-bold uppercase tracking-widest text-sm mt-2 text-slate-500">1st Med Bn Mission Planner</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm font-bold">
          <label className="block text-[10px] uppercase text-slate-400 mb-2">Duration (Days)</label>
          <input type="number" value={duration} onChange={(e) => setDuration(parseInt(e.target.value))} className="w-full border-2 border-slate-100 rounded p-2" min="1" />
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm col-span-2 font-bold">
          <label className="block text-[10px] uppercase text-slate-400 mb-2">Exercise Name</label>
          <div className="flex space-x-2">
            <input type="text" value={exerciseName} onChange={(e) => setExerciseName(e.target.value)} className="flex-1 border-2 border-slate-100 rounded p-2" />
            <button onClick={generateName} className="bg-blue-600 text-white px-4 rounded hover:bg-blue-700 transition font-black text-xs">{isGenerating ? "..." : "AI GEN"}</button>
          </div>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm font-bold">
          <label className="block text-[10px] uppercase text-slate-400 mb-2">AOR</label>
          <select value={aor} onChange={(e) => setAor(e.target.value)} className="w-full border-2 border-slate-100 rounded p-2"><option>Urban</option><option>Jungle</option><option>Arctic</option><option>Desert</option></select>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm font-bold">
          <label className="block text-[10px] uppercase text-slate-400 mb-2">Unit</label>
          <select value={unitType} onChange={(e) => setUnitType(e.target.value)} className="w-full border-2 border-slate-100 rounded p-2"><option>Division</option><option>CLB</option></select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
        <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
          <div className="flex justify-between items-center mb-6 border-b-2 pb-2">
            <h2 className="