"use client";
import React, { useState } from 'react';
import Link from 'next/link';

export default function TacticalPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState("");

  const handleGenerate = async () => {
    setLoading(true);
    const RAILWAY_URL = "https://role2-builder-production.up.railway.app"; 

    try {
      const warnoResponse = await fetch(`${RAILWAY_URL}/generate-warno`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exerciseName: "Exercise Steel Knight",
          duration: 3,
          aor: "Urban",
          mets: "MET 2, MET 5"
        })
      });
      const warnoData = await warnoResponse.json();
      setResult(warnoData.document);

      const mselResponse = await fetch(`${RAILWAY_URL}/generate-msel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exerciseName: "Exercise Steel Knight" })
      });

      const blob = await mselResponse.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = "Master_Scenario_Events_List.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (error) {
      console.error("Error:", error);
      setResult("Connection Error. Check if Railway is Online.");
    }
    setLoading(false);
  };

  return (
    <div className="max-w-5xl mx-auto p-8 bg-slate-50 min-h-screen font-sans text-slate-900">
      <header className="mb-8 border-b-2 border-slate-200 pb-4 flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-extrabold text-slate-900 uppercase tracking-tight">Step 2: Tactical Scenario</h1>
          <p className="text-slate-700 font-medium italic">Assign casualty waves and environmental stressors</p>
        </div>
        <Link href="/" className="text-blue-700 font-black hover:underline mb-1">← BACK TO SETUP</Link>
      </header>

      {/* Global AOR Settings */}
      <div className="bg-white p-6 rounded-lg shadow-md border border-slate-300 mb-8">
        <label className="block text-xs font-black text-slate-500 uppercase tracking-widest mb-2">Primary AOR</label>
        <select className="w-full border-2 border-slate-300 rounded p-3 font-bold bg-white">
          <option>Urban (Crush/Blast)</option>
          <option>Jungle (Heat/Immersion)</option>
          <option>Desert (Dehydration/Dust)</option>
        </select>
      </div>

      {/* Day Cards */}
      <div className="space-y-6">
        {[1, 2, 3].map(day => (
          <div key={day} className="bg-white p-6 rounded-xl shadow-md border border-slate-300 border-l-[12px] border-l-blue-800">
            <h3 className="font-black text-xl text-slate-900 uppercase mb-4">Day {day} Configuration</h3>
            <div className="grid grid-cols-3 gap-6">
              <div>
                <label className="block text-[10px] font-black text-slate-400 uppercase mb-1">Casualties</label>
                <input type="number" className="w-full border-2 border-slate-200 p-3 rounded-md font-bold" placeholder="Qty" />
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-400 uppercase mb-1">Operation</label>
                <select className="w-full border-2 border-slate-200 p-3 rounded-md font-bold">
                  <option>Frontal Attack</option>
                  <option>Amphibious Assault</option>
                  <option>Sustainment</option>
                </select>
              </div>
              <div className="flex items-center pt-4">
                <label className="flex items-center space-x-2 text-sm font-black uppercase cursor-pointer">
                  <input type="checkbox" className="h-5 w-5" /> <span>MASCAL</span>
                </label>
              </div>
            </div>
          </div>
        ))}
      </div>

      <button 
        onClick={handleGenerate}
        disabled={loading}
        className="mt-12 w-full bg-emerald-700 text-white font-black py-6 rounded-2xl shadow-2xl hover:bg-emerald-800 transition transform active:scale-[0.99] text-xl uppercase tracking-widest border-b-8 border-emerald-900 disabled:bg-slate-400"
      >
        {loading ? "GEMINI IS WRITING & PACKING EXCEL..." : "Generate WARNO & Download MSEL"}
      </button>

      {result && (
        <div className="mt-12 p-8 bg-white border-2 border-blue-200 rounded-xl shadow-inner mb-20">
          <h2 className="text-2xl font-black text-blue-900 uppercase mb-4">WARNO Preview</h2>
          <pre className="whitespace-pre-wrap font-mono text-sm text-slate-800 leading-relaxed p-4 bg-slate-50 rounded border">{result}</pre>
        </div>
      )}
    </div>
  );
}