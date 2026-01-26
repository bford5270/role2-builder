"use client";
import React from 'react';
import Link from 'next/link';

export default function TacticalPage() {
  return (
    <div className="max-w-5xl mx-auto p-8 bg-slate-50 min-h-screen font-sans text-slate-900">
      <header className="mb-8 border-b-2 border-slate-200 pb-4 flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-extrabold text-slate-900 uppercase tracking-tight">Step 2: Tactical Scenario</h1>
          <p className="text-slate-700 font-medium italic">Assign casualty waves and environmental stressors</p>
        </div>
        <Link href="/" className="text-blue-700 font-black hover:underline mb-1">← BACK TO SETUP</Link>
      </header>
      
      <div className="bg-white p-6 rounded-lg shadow-md border border-slate-300 mb-8">
        <div className="grid grid-cols-2 gap-8">
          <div>
            <label className="block text-xs font-black text-slate-500 uppercase tracking-widest">AOR Selection</label>
            <select className="mt-1 block w-full border-2 border-slate-300 rounded p-3 bg-white text-slate-900 font-bold focus:border-blue-500 outline-none">
              <option>Urban</option><option>Jungle</option><option>Desert</option><option>Arctic</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-black text-slate-500 uppercase tracking-widest">Supporting Unit</label>
            <select className="mt-1 block w-full border-2 border-slate-300 rounded p-3 bg-white text-slate-900 font-bold focus:border-blue-500 outline-none">
              <option>Division Assets</option><option>Combat Logistics Battalion (CLB)</option>
            </select>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        {[1, 2, 3].map(day => (
          <div key={day} className="bg-white p-6 rounded-xl shadow-md border border-slate-300 border-l-[12px] border-l-blue-800">
            <div className="flex justify-between items-center mb-6 border-b pb-2">
              <h3 className="font-black text-xl text-slate-900 uppercase">Day {day} Configuration</h3>
              <div className="flex space-x-6">
                <label className="flex items-center space-x-2 text-sm font-black text-slate-700 uppercase cursor-pointer">
                  <input type="checkbox" className="h-5 w-5" /> <span>MASCAL</span>
                </label>
                <label className="flex items-center space-x-2 text-sm font-black text-slate-700 uppercase cursor-pointer">
                  <input type="checkbox" className="h-5 w-5" /> <span>Detainee Ops</span>
                </label>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-6">
              <div>
                <label className="block text-[10px] font-black text-slate-400 uppercase mb-1">Operation Type</label>
                <select className="w-full border-2 border-slate-200 p-3 rounded-md text-slate-900 font-bold bg-slate-50 focus:border-blue-500">
                  <option>Amphibious Assault</option><option>Frontal Attack</option><option>Infiltration</option><option>Seizure</option><option>Feint</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-400 uppercase mb-1">Casualties</label>
                <input type="number" className="w-full border-2 border-slate-200 p-3 rounded-md text-slate-900 font-bold bg-slate-50 focus:border-blue-500" placeholder="Qty" />
              </div>
              <div>
                <label className="block text-[10px] font-black text-slate-400 uppercase mb-1">Evac Status</label>
                <select className="w-full border-2 border-blue-200 p-3 rounded-md text-blue-800 font-black bg-blue-50 focus:border-blue-600">
                  <option>Evac Open</option><option>Evac Limited (PCC Required)</option><option>Evac Denied (Full PCC Hold)</option>
                </select>
              </div>
            </div>
          </div>
        ))}
      </div>

      <button className="mt-12 w-full bg-emerald-700 text-white font-black py-6 rounded-2xl shadow-2xl hover:bg-emerald-800 transition transform active:scale-[0.99] text-xl uppercase tracking-widest border-b-8 border-emerald-900">
        Generate Exercise Documents & Sim Cases
      </button>
    </div>
  );
}