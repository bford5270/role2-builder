"use client";
import React, { useState, useEffect } from 'react';
import Link from 'next/link';

export default function TacticalPage() {
  const [daysCount, setDaysCount] = useState(3);
  const [mascalActive, setMascalActive] = useState<{[key: number]: boolean}>({});

  useEffect(() => {
    const saved = localStorage.getItem('exDuration');
    if (saved) setDaysCount(parseInt(saved));
  }, []);

  return (
    <div className="max-w-6xl mx-auto p-8 bg-slate-50 min-h-screen text-slate-900 font-sans">
      <header className="mb-8 border-b-8 border-blue-900 pb-4 flex justify-between items-end">
        <div><h1 className="text-4xl font-black uppercase italic tracking-tighter">Tactical Casualty Flow</h1>
          <p className="text-blue-700 font-bold uppercase tracking-widest text-[10px]">Operational Stressors & Wave Distribution</p>
        </div>
        <Link href="/" className="text-blue-800 font-black hover:underline mb-1 text-xs uppercase">← Back to Setup</Link>
      </header>

      <div className="space-y-8">
        {Array.from({ length: daysCount }).map((_, i) => (
          <div key={i} className="bg-white p-6 rounded-2xl shadow-xl border-l-[16px] border-blue-900 border-2 border-slate-200">
            <h2 className="text-2xl font-black uppercase italic mb-6 border-b pb-2">Day {i + 1} Configuration</h2>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
              <div><label className="block text-[10px] font-black uppercase text-slate-400 mb-1">Tactical Setting</label>
                <select className="w-full border-2 border-slate-200 p-2 font-bold rounded bg-slate-50 text-xs"><option>Frontal Attack</option><option>Amphibious Assault</option><option>Convoy Ops</option><option>Defensive Ops</option><option>Retrograde</option></select>
              </div>
              <div><label className="block text-[10px] font-black uppercase text-slate-400 mb-1">Total Patients / Waves</label>
                <div className="flex space-x-1"><input type="number" placeholder="Qty" className="w-1/2 border-2 border-slate-200 p-2 font-bold rounded bg-slate-50 text-xs" /><input type="number" placeholder="Waves" className="w-1/2 border-2 border-slate-200 p-2 font-bold rounded bg-slate-50 text-xs" /></div>
              </div>
              <div className="flex flex-wrap gap-2 pt-4 col-span-2">
                <label className="flex items-center space-x-1 bg-red-50 px-2 py-1 rounded border border-red-200 cursor-pointer">
                  <input type="checkbox" onChange={(e) => setMascalActive({...mascalActive, [i]: e.target.checked})} className="h-3 w-3" /><span className="text-[9px] font-black uppercase text-red-900">MASCAL</span>
                </label>
                {['CBRN', 'Detainee Ops'].map(opt => <label key={opt} className="flex items-center space-x-1 bg-slate-100 px-2 py-1 rounded border border-slate-300 cursor-pointer"><input type="checkbox" className="h-3 w-3" /><span className="text-[9px] font-black uppercase">{opt}</span></label>)}
              </div>
            </div>
            {mascalActive[i] && (
              <div className="mt-4 p-4 bg-red-50 rounded-xl border-2 border-red-100 grid grid-cols-3 gap-4">
                <div><label className="block text-[9px] font-black uppercase text-red-400 mb-1">MASCAL Stressor</label>
                  <select className="w-full border-2 border-red-200 p-2 font-bold rounded bg-white text-[10px] text-red-900"><option>Vehicle Rollover</option><option>IED / Fragmentation</option><option>GSW / Assault</option><option>Aviation Mishap</option></select>
                </div>
                <div><label className="block text-[9px] font-black uppercase text-red-400 mb-1">Qty</label><input type="number" defaultValue={15} className="w-full border-2 border-red-200 p-2 font-bold rounded bg-white text-[10px] text-red-900" /></div>
                <div><label className="block text-[9px] font-black uppercase text-red-400 mb-1">Waves</label><input type="number" defaultValue={1} className="w-full border-2 border-red-200 p-2 font-bold rounded bg-white text-[10px] text-red-900" /></div>
              </div>
            )}
          </div>
        ))}
      </div>
      <button className="mt-12 w-full bg-emerald-700 text-white font-black py-8 rounded-3xl shadow-2xl transition text-3xl uppercase tracking-tighter border-b-[12px] border-emerald-900">Generate WARNO & Download MSEL</button>
    </div>
  );
}