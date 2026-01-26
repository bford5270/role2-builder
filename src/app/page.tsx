"use client";
import React, { useState } from 'react';
import Link from 'next/link';

export default function SetupPage() {
  const [exerciseName, setExerciseName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [aor, setAor] = useState("Urban");
  const [supportingUnit, setSupportingUnit] = useState("1st Medical Battalion");
  const [selectedMETs, setSelectedMETs] = useState<string[]>([]);
  
  const MET_LIST = [
    'MET 1: Provide Task-Organized Forces', 'MET 2: Conduct Casualty Treatment', 
    'MET 3: Conduct Temporary Casualty Holding', 'MET 4: Conduct Casualty Evacuation', 
    'MET 5: Conduct Mass Casualty Operations', 'MET 6: Dental Services', 'MET 7: Medical Regulating'
  ];

  const handleSelectAllMETs = () => {
    if (selectedMETs.length === MET_LIST.length) setSelectedMETs([]);
    else setSelectedMETs(MET_LIST);
  };

  const generateName = async () => {
    setIsGenerating(true);
    try {
      const response = await fetch("https://role2-builder-production.up.railway.app/generate-name", { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ aor, supportingUnit })
      });
      const data = await response.json();
      setExerciseName(data.name);
    } catch (e) { setExerciseName("Operation Crimson Scalpel"); }
    setIsGenerating(false);
  };

  return (
    <div className="max-w-4xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <h1 className="text-4xl font-black mb-8 border-b-4 border-blue-900 pb-2 uppercase italic tracking-tighter">Role 2 Exercise Builder</h1>

      {/* Context Selection */}
      <section className="mb-8 bg-white p-6 rounded-xl shadow-md border-2 border-slate-200 grid grid-cols-2 gap-4">
        <div>
          <label className="block text-[10px] font-black uppercase text-slate-400 mb-2">Primary AOR</label>
          <select value={aor} onChange={(e) => setAor(e.target.value)} className="w-full border-2 border-slate-300 rounded-lg p-3 font-bold bg-slate-50">
            <option>Urban</option>
            <option>Jungle</option>
            <option>Arctic</option>
            <option>Desert</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-black uppercase text-slate-400 mb-2">Supporting Unit</label>
          <input 
            type="text" 
            value={supportingUnit} 
            onChange={(e) => setSupportingUnit(e.target.value)} 
            className="w-full border-2 border-slate-300 rounded-lg p-3 font-bold bg-slate-50"
          />
        </div>
      </section>

      {/* Name Generator */}
      <section className="mb-8 bg-white p-6 rounded-xl shadow-md border-2 border-slate-200">
        <label className="block text-xs font-black uppercase text-slate-400 mb-2">Exercise Designation</label>
        <div className="flex space-x-4">
          <input 
            type="text" 
            value={exerciseName}
            onChange={(e) => setExerciseName(e.target.value)}
            className="flex-1 border-2 border-slate-300 rounded-lg p-3 font-bold text-lg focus:border-blue-500 outline-none" 
            placeholder="e.g. Steel Knight" 
          />
          <button onClick={generateName} className="bg-blue-600 text-white px-6 rounded-lg font-black hover:bg-blue-700 transition active:scale-95">
            {isGenerating ? "GENERATING..." : "AI GENERATE NAME"}
          </button>
        </div>
      </section>

      {/* Evaluator Counts */}
      <section className="mb-8 grid grid-cols-3 gap-6">
        {['Medical Evaluators', 'Tactical Evaluators', 'Logistics Evaluators'].map((type) => (
          <div key={type} className="bg-white p-4 rounded-xl border-2 border-slate-200 shadow-sm text-center">
            <label className="block text-[10px] font-black uppercase text-slate-400 mb-2">{type}</label>
            <input type="number" defaultValue={2} className="w-full text-2xl font-black text-blue-900 border-b-2 border-slate-100 outline-none text-center" />
          </div>
        ))}
      </section>

      {/* MET Checklist */}
      <section className="mb-8 bg-white p-6 rounded-xl shadow-md border-2 border-slate-200">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-black text-slate-800 uppercase italic">MET Proficiency Focus</h2>
          <button onClick={handleSelectAllMETs} className="text-[10px] font-black bg-slate-100 border border-slate-300 px-3 py-1 rounded hover:bg-slate-200 uppercase">
            {selectedMETs.length === MET_LIST.length ? "Deselect All" : "Select All METs"}
          </button>
        </div>
        <div className="grid grid-cols-1 gap-2 bg-slate-50 p-4 rounded-lg">
          {MET_LIST.map(met => (
            <label key={met} className="flex items-center space-x-3 p-2 hover:bg-white rounded-md cursor-pointer transition">
              <input 
                type="checkbox" 
                checked={selectedMETs.includes(met)}
                onChange={() => {
                  if (selectedMETs.includes(met)) setSelectedMETs(selectedMETs.filter(m => m !== met));
                  else setSelectedMETs([...selectedMETs, met]);
                }}
                className="h-5 w-5 rounded border-slate-400" 
              />
              <span className="text-sm font-bold text-slate-700">{met}</span>
            </label>
          ))}
        </div>
      </section>

      <Link href="/tactical">
        <button className="w-full bg-slate-900 text-white font-black py-6 rounded-2xl shadow-2xl hover:bg-black transition text-xl uppercase tracking-widest border-b-8 border-slate-700 active:border-b-0 active:translate-y-1">
          Configure Tactical Phase →
        </button>
      </Link>
    </div>
  );
}