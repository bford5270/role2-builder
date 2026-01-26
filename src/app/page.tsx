"use client";
import React from 'react';
import Link from 'next/link';

export default function SetupPage() {
  return (
    <div className="max-w-4xl mx-auto p-8 bg-slate-50 min-h-screen font-sans text-slate-900">
      <header className="mb-8 border-b-2 border-slate-200 pb-4">
        <h1 className="text-4xl font-extrabold text-slate-900">Role 2 Exercise Builder</h1>
        <p className="text-slate-700 font-medium">Phase 1: Exercise Parameters & T&R Standards</p>
      </header>
      
      {/* 1. Basic Parameters */}
      <section className="mb-8 bg-white p-6 rounded-lg shadow-md border border-slate-300">
        <h2 className="text-xl font-bold mb-4 text-blue-900 underline decoration-blue-500 underline-offset-4">1. Exercise Info</h2>
        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-black text-slate-700 uppercase">Duration</label>
            <select className="mt-1 block w-full border-2 border-slate-300 rounded-md p-2 bg-white text-slate-900 font-bold focus:border-blue-500 outline-none">
              {[1, 2, 3, 4, 5, 7, 10, 14].map(d => <option key={d} className="text-slate-900">{d} Days</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-black text-slate-700 uppercase">Exercise Name</label>
            <input type="text" className="mt-1 block w-full border-2 border-slate-300 rounded-md p-2 bg-white text-slate-900 font-bold placeholder-slate-400 focus:border-blue-500 outline-none" placeholder="e.g. Steel Knight" />
          </div>
        </div>
      </section>

      {/* 2. T&R METs */}
      <section className="mb-8 bg-white p-6 rounded-lg shadow-md border border-slate-300">
        <h2 className="text-xl font-bold mb-4 text-blue-900 underline decoration-blue-500 underline-offset-4">2. MET Selection (NAVMC 3500.84A)</h2>
        <div className="space-y-2 max-h-60 overflow-y-auto p-2 border-2 border-slate-200 rounded bg-slate-50">
          {['MET 1: Provide Task-Organized Forces', 'MET 2: Conduct Casualty Treatment', 'MET 3: Conduct Temporary Casualty Holding', 'MET 4: Conduct Casualty Evacuation', 'MET 5: Conduct Mass Casualty Operations', 'MET 6: Dental Services', 'MET 7: Medical Regulating'].map(met => (
            <label key={met} className="flex items-center space-x-3 p-2 hover:bg-white rounded border border-transparent hover:border-slate-300 cursor-pointer transition-colors">
              <input type="checkbox" className="h-5 w-5 text-blue-700 rounded border-slate-400" />
              <span className="text-sm text-slate-900 font-bold">{met}</span>
            </label>
          ))}
        </div>
      </section>

      {/* 3. Functional Areas & Evaluators */}
      <section className="mb-8 bg-white p-6 rounded-lg shadow-md border border-slate-300">
        <h2 className="text-xl font-bold mb-4 text-blue-900 underline decoration-blue-500 underline-offset-4">3. Personnel & Capabilities</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 border-b pb-6">
          {['STP', 'FRSS', 'Holding', 'Lab', 'Radiology', 'ERC', 'Dental', 'Mortuary Affairs'].map(area => (
            <label key={area} className="flex items-center space-x-2">
              <input type="checkbox" className="h-5 w-5 text-blue-700" />
              <span className="text-sm font-black text-slate-800">{area}</span>
            </label>
          ))}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 pt-4">
          {['Critical Care Nurse', 'ERC Nurse', 'ER Nurse', 'Med Surg Nurse', 'FP', 'EM Doc', 'PA', 'General Surgeon', 'Orthopedic Surgeon', 'Anesthesiologist', 'Dentist'].map(spec => (
            <div key={spec}>
              <label className="block text-[10px] font-black text-slate-500 uppercase">{spec}</label>
              <input type="number" min="0" className="mt-1 block w-full border-2 border-slate-300 rounded p-2 text-sm text-slate-900 font-bold bg-white focus:border-blue-500 outline-none" placeholder="0" />
            </div>
          ))}
        </div>
      </section>

      <Link href="/tactical">
        <button className="w-full bg-blue-800 text-white font-black py-5 rounded-xl shadow-xl hover:bg-blue-900 transition transform active:scale-[0.98] text-lg uppercase tracking-tighter">
          Next: Build Tactical Scenario
        </button>
      </Link>
    </div>
  );
}