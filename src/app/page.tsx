"use client";
import React, { useState } from 'react';
import Link from 'next/link';

export default function SetupPage() {
  const [exerciseName, setExerciseName] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
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
      const response = await fetch("https://role2-builder-production.up.railway.app/generate-name", { method: 'POST' });
      const data = await response.json();
      setExerciseName(data.name);
    } catch (e) { setExerciseName("Operation Crimson Scalpel"); }
    setIsGenerating(false);
  };

  return (
    <div className="max-w-4xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <h1 className="text-4xl font-black mb-8 border-b-4 border-blue-900 pb-2 uppercase italic">Role 2 Builder</h1>

      {/* Exercise Name with Gemini Generator */}
      <section className="mb-8 bg-white p-6 rounded-xl shadow-md border-2 border-slate-200">
        <label className="block text-sm font-black uppercase text-slate-500 mb-2">Exercise Name</label>
        <div className="flex space-x-4">
          <input 
            type="text" 
            value={exerciseName}
            onChange={(e) => setExerciseName(e.target.value)}
            className="flex-1 border-2 border-slate-300 rounded-lg p-3 font-bold text-lg" 
            placeholder="e.g. Steel Knight" 
          />
          <button 
            onClick={generateName}
            className="bg-blue-600 text-white px-6 rounded-lg font-black hover:bg-blue-700 transition"
          >
            {isGenerating ? "GENERATING..." : "AI GENERATE NAME"}
          </button>
        </div>
      </section>

      {/* METs with Select All */}
      <section className="mb-8 bg-white p-6 rounded-xl shadow-md border-2 border-slate-200">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-blue-900 uppercase">MET Selection</h2>
          <button 
            onClick={handleSelectAllMETs}
            className="text-xs font-black bg-slate-200 px-3 py-1 rounded hover:bg-slate-300"
          >
            {selectedMETs.length === MET_LIST.length ? "DESELECT ALL" : "SELECT ALL"}
          </button>
        </div>
        <div className="grid grid-cols-1 gap-2 p-4 bg-slate-50 rounded-lg border-2 border-slate-100">
          {MET_LIST.map(met => (
            <label key={met} className="flex items-center space-x-3 p-2 hover:bg-white rounded cursor-pointer transition">
              <input 
                type="checkbox" 
                checked={selectedMETs.includes(met)}
                onChange={() => {
                  if (selectedMETs.includes(met)) setSelectedMETs(selectedMETs.filter(m => m !== met));
                  else setSelectedMETs([...selectedMETs, met]);
                }}
                className="h-5 w-5 border-2 border-slate-400" 
              />
              <span className="text-sm font-bold">{met}</span>
            </label>
          ))}
        </div>
      </section>

      <Link href="/tactical">
        <button className="w-full bg-slate-900 text-white font-black py-5 rounded-2xl shadow-xl hover:bg-black transition text-xl uppercase tracking-widest border-b-8 border-slate-700">
          Configure Tactical Phase →
        </button>
      </Link>
    </div>
  );
}