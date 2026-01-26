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
      // Logic for WARNO and MSEL download
      const warnoResponse = await fetch(`${RAILWAY_URL}/generate-warno`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exerciseName: "Steel Knight", duration: 3, aor: "Urban", mets: "MET 2, MET 5" })
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
      a.href = url; a.download = "MSEL_Final.xlsx";
      document.body.appendChild(a); a.click(); a.remove();
    } catch (error) {
      setResult("Connection Error. Ensure Railway is live.");
    }
    setLoading(false);
  };

  return (
    <div className="max-w-5xl mx-auto p-8 bg-slate-50 min-h-screen font-sans text-slate-900">
      <header className="mb-8 border-b-4 border-slate-200 pb-4 flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-black text-slate-900 uppercase tracking-tighter italic">Step 2: Tactical Scenario</h1>
          <p className="text-slate-500 font-bold uppercase text-xs tracking-widest">Casualty Waves & Environmental Stressors</p>
        </div>
        <Link href="/" className="text-blue-700 font-black hover:underline mb-1 text-sm uppercase">← Back to Setup</Link>
      </header>

      {/* Global AOR Settings */}
      <div className="bg-white p-6 rounded-xl shadow-md border-2 border-slate-200 mb-8 grid grid-cols-2 gap-8">
        <div>
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Primary AOR</label>
          <select className="w-full border-2 border-slate-200 rounded-lg p-3 font-bold bg-slate-50">
            <option>Urban (Crush/Blast)</option>
            <option>Jungle (Heat/Immersion)</option>
            <option>Arctic (Cold/Hypothermia)</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Patient Distribution (Waves)</label>
          <input type="number" defaultValue={3} className="w-full border-2 border-slate-200 rounded-lg p-3 font-bold bg-slate-50" />
        </div>
      </div>

      {/* Day Configuration Cards */}
      <div className="space-y-6">
        {[1, 2, 3].map(day => (
          <div key={day} className="bg-white p-6 rounded-xl shadow-lg border-2 border-slate-200 border-l-[16px] border-l-blue-900">
            <div className="flex justify-between items-center mb-6 border-b-2 border-slate-100 pb-4">
              <h3 className="font-black text-2xl text-slate-900 uppercase italic">Day {day}</h3>
              <div className="flex space-x-4">
                {['MASCAL', 'CBRN', 'Night Ops'].map(opt => (
                  <label key={opt} className="flex items-center space-x-2 bg-slate-100 px-3 py-1 rounded-full border border-slate-200 cursor-pointer hover:bg-white transition">
                    <input type="checkbox" className="h-4 w-4" />
                    <span className="text-[10px] font-black uppercase text-slate-600">{opt}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-8">
              <div>
                <label className="block text-[10px] font-black text-slate-400 uppercase mb-1">Op Type</label>
                <select className="w-full border-2 border-slate-200 p-3 rounded-lg font-bold bg-slate-50">
                  <option>Frontal Attack</option>
                  <option>Amphibious Assault</option>
                  <option>Defensive Ops</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-400 uppercase mb-1">Total Expected WIA</label>
                <input type="number" className="w-full border-2 border-slate-200 p-3 rounded-lg font-bold bg-slate-50" placeholder="0" />
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-400 uppercase mb-1">Evac Status</label>
                <select className="w-full border-2 border-blue-100 p-3 rounded-lg font-bold bg-blue-50 text-blue-900">
                  <option>Open (Standard)</option>
                  <option>Denied (Stay/Hold)</option>
                  <option>Limited (Weather)</option>
                </select>
              </div>
            </div>
          </div>
        ))}
      </div>

      <button onClick={handleGenerate} disabled={loading} className="mt-12 w-full bg-emerald-700 text-white font-black py-8 rounded-3xl shadow-2xl hover:bg-emerald-800 transition transform active:scale-[0.98] text-2xl uppercase tracking-tighter border-b-[12px] border-emerald-900 disabled:bg-slate-400">
        {loading ? "AI IS PACKING YOUR GEAR..." : "Generate WARNO & Download MSEL"}
      </button>

      {result && (
        <div className="mt-12 p-8 bg-white border-4 border-blue-900 rounded-3xl shadow-2xl mb-20">
          <h2 className="text-3xl font-black text-blue-900 uppercase italic mb-6 tracking-tighter">Draft Operation Order / Annex Q</h2>
          <pre className="whitespace-pre-wrap font-mono text-sm text-slate-800 leading-relaxed p-6 bg-slate-50 rounded-xl border-2 border-slate-200 italic shadow-inner">{result}</pre>
        </div>
      )}
    </div>
  );
}