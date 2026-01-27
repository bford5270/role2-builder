"use client";
import React, { useState } from 'react';
import Link from 'next/link';

export default function SetupPage() {
  const [exerciseName, setExerciseName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [aor, setAor] = useState("Urban");
  const [unitType, setUnitType] = useState("Division");
  const [selectedMETs, setSelectedMETs] = useState<string[]>([]);
  const [selectedSpaces, setSelectedSpaces] = useState<string[]>([]);
  const [expandedMET, setExpandedMET] = useState<string | null>(null);
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null);

  const MET_DATA = [
    { 
      id: 'MET 1', name: 'Provide Task-Organized Forces', 
      events: [
        { id: 'HSS-PLAN-7001', name: 'Conduct planning', pecls: ['Problem Framing', 'Planning Process', 'Timeline', 'Issue WARNO', 'Create Orders'] },
        { id: 'HSS-PLAN-6001', name: 'Conduct planning', pecls: ['Problem Framing', 'Planning Process', 'Timeline', 'Issue WARNO', 'Create Orders'] }
      ] 
    },
    { 
      id: 'MET 2', name: 'Conduct Casualty Treatment', 
      events: [
        { id: 'HSS-MBN-6001', name: 'Establish resuscitative/surgical capabilities', pecls: ['Provide FRSS', 'Provide STP', 'Provide temp holding'] },
        { id: 'HSS-AID-5601', name: 'Provide Aid Station Health Services Support', pecls: ['Triage', 'Treat', 'Stabilize', 'Casualty Reports', 'DNBI'] },
        { id: 'HSS-STP-5001', name: 'Establish a resuscitative facility', pecls: ['Identify lift', 'Move to location', 'Employ tentage', 'Establish comms'] },
        { id: 'HSS-SVCS-3507', name: 'Perform medical care', pecls: ['Triage', 'History/PE', 'ID injury', 'Render treatment', 'Document'] }
      ] 
    },
    { 
      id: 'MET 3', name: 'Conduct Temporary Casualty Holding', 
      events: [
        { id: 'HSS-SVCS-3502', name: 'Conduct temporary casualty holding', pecls: ['Assess casualty', 'Provide holding', 'Maintain accountability', 'Document treatment'] }
      ] 
    },
    { 
      id: 'MET 4', name: 'Conduct Casualty Evacuation', 
      events: [
        { id: 'HSS-SVCS-3401', name: 'Conduct casualty evacuation', pecls: ['Submit request', 'Prepare casualty', 'Prepare documentation', 'Casualty turnover'] },
        { id: 'HSS-PET-4701', name: 'Coordinate patient movement', pecls: ['Receive request', 'Determine means', 'Determine destination', 'Track movement'] }
      ] 
    },
    { 
      id: 'MET 5', name: 'Conduct Mass Casualty Operations', 
      events: [
        { id: 'HSS-SVCS-3701', name: 'Perform mass casualty', pecls: ['Determine nature', 'Activate plan', 'Conduct triage', 'Emergency treatment', 'Evacuate'] }
      ] 
    },
    { 
      id: 'MET 6', name: 'Conduct and Provide Dental Services', 
      events: [
        { id: 'HSS-DENT-3001', name: 'Provide dental services', pecls: ['Triage', 'History/PE', 'ID injury', 'Render care', 'Document'] },
        { id: 'HSS-DENT-3002', name: 'Perform emergency dental treatment', pecls: ['Triage', 'History/PE', 'ID injury', 'Render care', 'Document'] }
      ] 
    },
    { 
      id: 'MET 7', name: 'Conduct Medical Regulating Services', 
      events: [
        { id: 'HSS-OPS-6001', name: 'Provide command and control', pecls: ['Medical watch', 'Battle rhythm', 'Execute IM', 'Maintain COP'] }
      ] 
    }
  ];

  const FOOTPRINT = ['STP', 'FRSS', 'Holding', 'Mortuary Affairs', 'Lab', 'Radiology', 'COC', 'Dental'];
  const SPECIALTIES = ['ERC nurse', 'Med Surg Nurse', 'ER Nurse', 'Critical Care Nurse', 'Family Physician', 'EM Doc', 'Anesthesiologist', 'Surgeon', 'Orthopedic Surgeon'];

  const toggleAllSpaces = () => {
    if (selectedSpaces.length === FOOTPRINT.length) setSelectedSpaces([]);
    else setSelectedSpaces(FOOTPRINT);
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
    } catch (e) { setExerciseName("Operation Obsidian Shield"); }
    setIsGenerating(false);
  };

  return (
    <div className="max-w-6xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <header className="mb-10 border-b-8 border-blue-900 pb-4">
        <h1 className="text-5xl font-black uppercase italic tracking-tighter">Role 2 Exercise Builder</h1>
        <p className="text-blue-700 font-bold uppercase tracking-widest text-sm mt-2">1st Med Bn Mission Planner</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200">
          <label className="block text-[10px] font-black uppercase text-slate-400 mb-2">Primary AOR</label>
          <select value={aor} onChange={(e) => setAor(e.target.value)} className="w-full border-2 border-slate-200 rounded p-2 font-bold bg-slate-50 outline-none">
            <option>Urban</option><option>Jungle</option><option>Arctic</option><option>Desert</option>
          </select>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200">
          <label className="block text-[10px] font-black uppercase text-slate-400 mb-2">Supported Unit</label>
          <select value={unitType} onChange={(e) => setUnitType(e.target.value)} className="w-full border-2 border-slate-200 rounded p-2 font-bold bg-slate-50 outline-none">
            <option>Division</option><option>CLB</option>
          </select>
        </div>
        <div className="bg-white p-4 rounded-xl border-2 border-slate-200 col-span-2 shadow-sm">
          <label className="block text-[10px] font-black uppercase text-slate-400 mb-2">Exercise Name</label>
          <div className="flex space-x-2">
            <input type="text" value={exerciseName} onChange={(e) => setExerciseName(e.target.value)} className="flex-1 border-2 border-slate-300 rounded p-2 font-bold" />
            <button onClick={generateName} className="bg-blue-600 text-white px-4 rounded font-black text-xs hover:bg-blue-700 transition active:scale-95">{isGenerating ? "..." : "AI GEN"}</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
        <section className="bg-white p-6 rounded-2xl shadow-xl border-2 border-slate-200">
          <div className="flex justify-between items-center mb-6 border-b-2 pb-2">
            <h2 className="text-xl font-black uppercase italic text-slate-800">HSS T&R METL</h2>
            <button onClick={() => setSelectedMETs(selectedMETs.length === MET_DATA.length ? [] : MET_DATA.map(m => m.id))} className="text-[10px] font-black bg-slate-900 text-white px-3 py-1 rounded-full uppercase">Select All</button>
          </div>
          <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
            {MET_DATA.map(met => (
              <div key={met.id} className="border-2 border-slate-100 rounded-lg overflow-hidden">
                <div className="flex items-center p-3 bg-slate-50 hover:bg-blue-50 transition cursor-pointer">
                  <input type="checkbox" checked={selectedMETs.includes(met.id)} onChange={() => setSelectedMETs(selectedMETs.includes(met.id) ? selectedMETs.filter(id => id !== met.id) : [...selectedMETs, met.id])} className="h-5 w-5 mr-4" />
                  <div className="flex-1 font-bold text-[10px] uppercase" onClick={() => setExpandedMET(expandedMET === met.id ? null : met.id)}>{met.id}: {met.name}</div>
                  <div className="font-black text-lg">{expandedMET === met.id ? '▾' : '▸'}</div>
                </div>
                {expandedMET === met.id && (
                  <div className="p-4 bg-white border-t-2 border-slate-50 space-y-4">
                    {met.events.map(event => (
                      <div key={event.id} className="space-y-2">
                        <div className="flex justify-between items-center cursor-pointer p-2 bg-slate-50 rounded border border-slate-200" onClick={() => setExpandedEvent(expandedEvent === event.id ? null : event.id)}>
                          <span className="text-[10px] font-bold text-blue-900 uppercase">{event.id}: {event.name}</span>
                          <span className="text-xs">{expandedEvent === event.id ? '▾' : '▸'}</span>
                        </div>
                        {expandedEvent === event.id && (
                          <div className="grid grid-cols-1 gap-1 pl-4">
                            {event.pecls.map(pecl => (
                              <div key={pecl} className="text-[10px] text-slate-600 border-l-2 border-blue-200 pl-3 font-mono py-1">{pecl}</div>
                            ))}
                          </div>
                        )}
                      </div>