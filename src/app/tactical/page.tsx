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
        body: JSON.stringify({ exerciseName: "Steel Knight", selectedMETs: "MET 2, MET 5" })
      });
      const warnoData = await warnoResponse.json();
      setResult(warnoData.document);

      const mselResponse = await fetch(`${RAILWAY_URL}/generate-msel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exerciseName: "Steel Knight" })
      });
      const blob = await mselResponse.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = "MSEL_1stMedBn.xlsx";
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) { setResult("Backend Connection Error."); }
    setLoading(false);
  };

  return (
    <div className="max-w-6xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <header className="mb-8 border-b-8 border-blue-900 pb-4 flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-black uppercase italic tracking-tighter">Tactical Casualty Flow</h1>
          <p className="text-blue-700 font-bold uppercase tracking-widest text-[10px]">Operational Stressors & Wave Distribution</p>
        </div>
        <Link href="/" className="text-blue-800 font-black hover:underline mb-1 text-xs uppercase">← Back to Setup</Link>
      </header>

      <div className="space-y-6">
        {[1, 2, 3].map(day => (
          <div key={day} className="bg-white p-6 rounded-2xl shadow-xl border-l-[16px] border-blue-900 border-2 border-slate-200">
            <h2 className="text-2xl font-black uppercase italic mb-6 border-b pb-2">Day {day} Configuration</h2>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <div>
                <label className="block text-[10px] font-black uppercase text-slate-400 mb-1">Movement Type</label>
                <select className="w-full border-2 border-slate-200 p-2 font-bold rounded bg-slate-50">
                  <option>Frontal Attack</option><option>Amphibious Assault</option>
                  <option>Convoy Ops</option><option>Defensive Ops</option><option>Retrograde</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase text-slate-400 mb-1">Casualty Waves</label>
                <input type="number" defaultValue={3} className="w-full border-2 border-slate-200 p-2 font-bold rounded bg-slate-50" />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase text-slate-400 mb-1">MASCAL Type</label>
                <select className="w-full border-2 border-slate-200 p-2 font-bold rounded bg-slate-50 text-red-700">
                  <option>None</option><option>Vehicle Rollover</option>
                  <option>IED / Fragmentation</option><option>GSW / Assault</option><option>CBRN</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase text-slate-400 mb-1">Evac Status</label>
                <select className="w-full border-2 border-slate-200 p-2 font-bold rounded bg-blue-50">
                  <option>Open (All Platforms)</option><option>Denied (Stay/Hold)</option><option>Limited (Weather)</option>
                </select>
              </div>
            </div>
          </div>
        ))}
      </div>

      <button onClick={handleGenerate} disabled={loading} className="mt-12 w-full bg-emerald-700 text-white font-black py-8 rounded-3xl shadow-2xl hover:bg-emerald-800 transition text-3xl uppercase tracking-tighter border-b-[12px] border-emerald-900">
        {loading ? "GENERATING MISSION ASSETS..." : "Generate WARNO & Download MSEL"}
      </button>

      {result && (
        <div className="mt-12 p-8 bg-white border-4 border-blue-900 rounded-3xl shadow-2xl mb-20">
          <h2 className="text-2xl font-black uppercase italic mb-4">Draft Warning Order</h2>
          <pre className="whitespace-pre-wrap font-mono text-sm p-4 bg-slate-50 rounded border">{result}</pre>
        </div>
      )}
    </div>
  );
}