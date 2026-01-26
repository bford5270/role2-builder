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
      // 1. Generate the WARNO Text
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

      // 2. Generate and Download the MSEL Excel Spreadsheet
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
      
      {/* ... (Keep your Daily Scenario Cards here) ... */}
      <div className="bg-blue-900 text-white p-4 rounded mb-8 text-center font-bold">
        MSEL Generation Active: Clicking generate will now download an Excel file.
      </div>

      <button 
        onClick={handleGenerate}
        disabled={loading}
        className="mt-12 w-full bg-emerald-700 text-white font-black py-6 rounded-2xl shadow-2xl hover:bg-emerald-800 transition transform active:scale-[0.99] text-xl uppercase tracking-widest border-b-8 border-emerald-900 disabled:bg-slate-400"
      >
        {loading ? "GEMINI IS WORKING..." : "Generate WARNO & Download MSEL"}
      </button>

      {result && (
        <div className="mt-12 p-8 bg-white border-2 border-blue-200 rounded-xl shadow-inner mb-20">
          <h2 className="text-2xl font-black text-blue-900 uppercase mb-4">WARNO Draft</h2>
          <pre className="whitespace-pre-wrap font-mono text-sm text-slate-800 leading-relaxed p-4 bg-slate-50 rounded border">
            {result}
          </pre>
        </div>
      )}
    </div>
  );
}