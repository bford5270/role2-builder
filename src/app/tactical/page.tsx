'use client';

import React, { useState, useEffect } from 'react';

interface DayConfig {
  day_number: number;
  tactical_setting: string;
  total_patients: number;
  total_waves: number;
  night_ops: boolean;
  mascal: boolean;
  mascal_etiology: string | null;
  mascal_patients: number | null;
  cbrn: boolean;
  detainee_ops: boolean;
}

interface ExerciseConfig {
  exercise_name: string;
  duration: number;
  supported_unit: string;
  environment: string;
  threat_level: string;
  region: string;
  selected_mets: string[];
  selected_footprint: string[];
  specialists: Record<string, number>;
  days: DayConfig[];
}

const TACTICAL_SETTINGS = [
  'Frontal Attack',
  'Amphibious Assault',
  'Convoy Operations',
  'Defensive Operations',
  'Retrograde Operations',
  'Stability Operations',
  'Humanitarian Assistance'
];

const MASCAL_ETIOLOGIES = [
  'IED/Blast',
  'Vehicle Rollover',
  'GSW/Small Arms',
  'Aviation Mishap',
  'Indirect Fire/Mortar',
  'Structural Collapse',
  'Burns/Fire',
  'Drowning (Amphibious)',
  'VBIED'
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://role2-builder-production.up.railway.app';

export default function TacticalScenarioPage() {
  const [config, setConfig] = useState<ExerciseConfig | null>(null);
  const [days, setDays] = useState<DayConfig[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string>('');
  const [progressPct, setProgressPct] = useState(0);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadName, setDownloadName] = useState<string>('');

  useEffect(() => {
    const savedConfig = localStorage.getItem('exerciseConfig');
    if (savedConfig) {
      const parsed = JSON.parse(savedConfig) as ExerciseConfig;
      setConfig(parsed);
      
      const initialDays: DayConfig[] = Array.from({ length: parsed.duration }, (_, i) => ({
        day_number: i + 1,
        tactical_setting: 'Defensive Operations',
        total_patients: 8,
        total_waves: 3,
        night_ops: false,
        mascal: false,
        mascal_etiology: null,
        mascal_patients: null,
        cbrn: false,
        detainee_ops: false
      }));
      setDays(initialDays);
    }
  }, []);

  const updateDay = (dayIndex: number, field: keyof DayConfig, value: any) => {
    setDays(prev => {
      const updated = [...prev];
      updated[dayIndex] = { ...updated[dayIndex], [field]: value };
      if (field === 'mascal' && !value) {
        updated[dayIndex].mascal_etiology = null;
        updated[dayIndex].mascal_patients = null;
      }
      return updated;
    });
  };

  const copyDayConfig = (fromIndex: number) => {
    if (fromIndex < days.length - 1) {
      setDays(prev => {
        const updated = [...prev];
        for (let i = fromIndex + 1; i < updated.length; i++) {
          updated[i] = { ...updated[fromIndex], day_number: i + 1 };
        }
        return updated;
      });
    }
  };

  const handleGenerate = async () => {
    if (!config) return;

    setGenerating(true);
    setError(null);
    setDownloadUrl(null);
    setProgress('Starting...');
    setProgressPct(2);

    try {
      const fullConfig: ExerciseConfig = { ...config, days };
      const resp = await fetch(`${API_BASE}/generate-exercise`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fullConfig)
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || 'Failed to start generation');
      }

      const data = await resp.json();
      const job_id: string = data.job_id;
      if (!job_id) throw new Error('Server did not return a job ID');

      while (true) {
        await new Promise(r => setTimeout(r, 2000));

        let statusResp: Response;
        try {
          statusResp = await fetch(`${API_BASE}/jobs/${job_id}`);
        } catch (fetchErr) {
          throw new Error(`Cannot reach server at ${API_BASE} — check CORS or network`);
        }
        if (!statusResp.ok) throw new Error(`Server error ${statusResp.status} on job poll`);
        const job = await statusResp.json();

        if (job.status === 'error') throw new Error(job.error || 'Generation failed');

        setProgress(job.progress);
        if (job.total > 0) {
          const casePct = Math.round((job.completed / job.total) * 75);
          setProgressPct(5 + casePct);
        }
        if (job.progress.includes('documents')) setProgressPct(82);
        if (job.progress.includes('Assembling')) setProgressPct(93);

        if (job.status === 'complete') {
          setProgressPct(100);
          const dlResp = await fetch(`${API_BASE}/download/${job.token}`);
          const blob = await dlResp.blob();
          const url = window.URL.createObjectURL(blob);
          setDownloadUrl(url);
          setDownloadName(job.filename);
          break;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setProgress('');
      setProgressPct(0);
    } finally {
      setGenerating(false);
    }
  };

  const getTotalCasualties = () => days.reduce((sum, d) => sum + d.total_patients, 0);

  if (!config) {
    return (
      <div className="min-h-screen bg-surface-0 text-ink-1 p-8 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-xl font-medium font-display mb-4 text-ink-1">No exercise configuration found.</h2>
          <a href="/" className="text-accent hover:text-accent-hover underline">← Return to setup</a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-0 text-ink-1 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold font-display tracking-display text-ink-1">{config.exercise_name}</h1>
            <p className="text-ink-3 text-sm font-mono">{config.duration} days · {config.environment} · {config.region} · {config.threat_level}</p>
          </div>
          <a href="/" className="text-accent hover:text-accent-hover text-sm">← Back to Setup</a>
        </div>

        <div className="bg-surface-1 border border-border-1 rounded p-4 mb-6 grid grid-cols-4 gap-4 text-center">
          <div><div className="text-3xl font-mono font-medium text-ink-1">{config.duration}</div><div className="text-xs uppercase tracking-caps text-ink-3 mt-1">Days</div></div>
          <div><div className="text-3xl font-mono font-medium text-ink-1">{getTotalCasualties()}</div><div className="text-xs uppercase tracking-caps text-ink-3 mt-1">Total casualties</div></div>
          <div><div className="text-3xl font-mono font-medium text-signal-red">{days.filter(d => d.mascal).length}</div><div className="text-xs uppercase tracking-caps text-ink-3 mt-1">MASCAL events</div></div>
          <div><div className="text-3xl font-mono font-medium text-signal-amber">{days.filter(d => d.cbrn).length}</div><div className="text-xs uppercase tracking-caps text-ink-3 mt-1">CBRN drills</div></div>
        </div>

        <div className="space-y-4 mb-8">
          {days.map((day, idx) => (
            <div key={idx} className="bg-surface-1 border border-border-1 rounded p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-medium font-display text-ink-1">Day {day.day_number}</h3>
                {idx < days.length - 1 && (
                  <button onClick={() => copyDayConfig(idx)} className="text-xs text-ink-3 hover:text-accent transition-colors">Copy to remaining days →</button>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div>
                  <label className="block text-xs text-ink-3 mb-1">Tactical Setting</label>
                  <select value={day.tactical_setting} onChange={(e) => updateDay(idx, 'tactical_setting', e.target.value)} className="w-full bg-surface-2 border border-border-2 rounded px-3 py-2 text-sm">
                    {TACTICAL_SETTINGS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-ink-3 mb-1">Total Patients</label>
                  <input type="number" min="1" max="50" value={day.total_patients} onChange={(e) => updateDay(idx, 'total_patients', parseInt(e.target.value) || 1)} className="w-full bg-surface-2 border border-border-2 rounded px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-xs text-ink-3 mb-1">Number of Waves</label>
                  <input type="number" min="1" max="10" value={day.total_waves} onChange={(e) => updateDay(idx, 'total_waves', parseInt(e.target.value) || 1)} className="w-full bg-surface-2 border border-border-2 rounded px-3 py-2 text-sm" />
                </div>
                <div className="flex items-center">
                  <label className="flex items-center cursor-pointer">
                    <input type="checkbox" checked={day.night_ops} onChange={(e) => updateDay(idx, 'night_ops', e.target.checked)} className="sr-only" />
                    <div className={`w-10 h-5 rounded-full transition-colors ${day.night_ops ? 'bg-accent' : 'bg-surface-3'}`}>
                      <div className={`w-4 h-4 rounded-full bg-ink-1 mt-0.5 transition-transform ${day.night_ops ? 'translate-x-5' : 'translate-x-0.5'}`} />
                    </div>
                    <span className="ml-2 text-sm">Night Ops (1900-0700)</span>
                  </label>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-border-1">
                <div className="text-xs text-ink-3 mb-2">Operational Stressors</div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-surface-2 rounded p-3">
                    <label className="flex items-center cursor-pointer mb-2">
                      <input type="checkbox" checked={day.mascal} onChange={(e) => updateDay(idx, 'mascal', e.target.checked)} className="sr-only" />
                      <div className={`w-10 h-5 rounded-full transition-colors ${day.mascal ? 'bg-signal-red' : 'bg-surface-3'}`}>
                        <div className={`w-4 h-4 rounded-full bg-ink-1 mt-0.5 transition-transform ${day.mascal ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </div>
                      <span className="ml-2 text-sm font-medium text-signal-red">MASCAL</span>
                    </label>
                    {day.mascal && (
                      <div className="space-y-2 mt-2">
                        <select value={day.mascal_etiology || ''} onChange={(e) => updateDay(idx, 'mascal_etiology', e.target.value)} className="w-full bg-surface-2 border border-border-2 rounded px-2 py-1 text-xs">
                          <option value="">Select Etiology</option>
                          {MASCAL_ETIOLOGIES.map(e => <option key={e} value={e}>{e}</option>)}
                        </select>
                        <input type="number" placeholder="MASCAL patients" min="3" max="20" value={day.mascal_patients || ''} onChange={(e) => updateDay(idx, 'mascal_patients', parseInt(e.target.value) || null)} className="w-full bg-surface-2 border border-border-2 rounded px-2 py-1 text-xs" />
                      </div>
                    )}
                  </div>
                  <div className="bg-surface-2 rounded p-3">
                    <label className="flex items-center cursor-pointer">
                      <input type="checkbox" checked={day.cbrn} onChange={(e) => updateDay(idx, 'cbrn', e.target.checked)} className="sr-only" />
                      <div className={`w-10 h-5 rounded-full transition-colors ${day.cbrn ? 'bg-signal-amber' : 'bg-surface-3'}`}>
                        <div className={`w-4 h-4 rounded-full bg-ink-1 mt-0.5 transition-transform ${day.cbrn ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </div>
                      <span className="ml-2 text-sm font-medium text-signal-amber">CBRN Drill</span>
                    </label>
                    {day.cbrn && <p className="text-xs text-ink-3 mt-2">1-hour drill, all clinical ops paused</p>}
                  </div>
                  <div className="bg-surface-2 rounded p-3">
                    <label className="flex items-center cursor-pointer">
                      <input type="checkbox" checked={day.detainee_ops} onChange={(e) => updateDay(idx, 'detainee_ops', e.target.checked)} className="sr-only" />
                      <div className={`w-10 h-5 rounded-full transition-colors ${day.detainee_ops ? 'bg-signal-blue' : 'bg-surface-3'}`}>
                        <div className={`w-4 h-4 rounded-full bg-ink-1 mt-0.5 transition-transform ${day.detainee_ops ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </div>
                      <span className="ml-2 text-sm font-medium text-signal-blue">Detainee Ops</span>
                    </label>
                    {day.detainee_ops && <p className="text-xs text-ink-3 mt-2">Includes detainee medical scenarios</p>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {error && <div className="bg-surface-2 border-l-4 border-signal-red rounded p-4 mb-6"><p className="text-signal-red">{error}</p></div>}

        {progress && (
          <div className="bg-surface-1 border border-signal-amber rounded p-4 mb-6">
            <div className="flex items-center mb-2">
              {generating && <svg className="animate-spin h-5 w-5 mr-3 text-accent flex-shrink-0" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>}
              <p className="text-accent-hover">{progress}</p>
            </div>
            <div className="w-full bg-surface-3 rounded-full h-2">
              <div
                className="bg-accent-hover h-2 rounded-full transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        )}

        <div className="flex justify-center">
          <button
            onClick={handleGenerate}
            disabled={generating || days.some(d => d.mascal && !d.mascal_etiology)}
            className={`px-8 py-3 rounded font-semibold uppercase tracking-caps text-base transition-colors ${generating || days.some(d => d.mascal && !d.mascal_etiology) ? 'bg-surface-2 text-ink-3 cursor-not-allowed' : 'bg-accent hover:bg-accent-hover text-accent-on'}`}
          >
            {generating ? 'Generating exercise package...' : 'Generate all documents'}
          </button>
        </div>

        {days.some(d => d.mascal && !d.mascal_etiology) && <p className="text-center text-signal-red text-sm mt-2">Select a MASCAL etiology for all MASCAL days.</p>}

        <div className="mt-8 bg-surface-1 border border-border-1 rounded p-4">
          <h3 className="font-medium font-display text-ink-1 mb-3">Package contents</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-sm">
            <div className="bg-surface-2 border border-border-1 rounded p-3 text-center">
              <div className="text-xs uppercase tracking-caps text-ink-3 mb-1">MSEL</div>
              <div className="font-mono text-xs text-ink-2">.xlsx</div>
            </div>
            <div className="bg-surface-2 border border-border-1 rounded p-3 text-center">
              <div className="text-xs uppercase tracking-caps text-ink-3 mb-1">WARNO</div>
              <div className="font-mono text-xs text-ink-2">.docx</div>
            </div>
            <div className="bg-surface-2 border border-border-1 rounded p-3 text-center">
              <div className="text-xs uppercase tracking-caps text-ink-3 mb-1">Annex Q</div>
              <div className="font-mono text-xs text-ink-2">.docx</div>
            </div>
            <div className="bg-surface-2 border border-border-1 rounded p-3 text-center">
              <div className="text-xs uppercase tracking-caps text-ink-3 mb-1">MEDROE</div>
              <div className="font-mono text-xs text-ink-2">.docx</div>
            </div>
            <div className="bg-surface-2 border border-border-1 rounded p-3 text-center">
              <div className="text-xs uppercase tracking-caps text-ink-3 mb-1">Case book</div>
              <div className="font-mono text-xs text-ink-2">.docx</div>
            </div>
          </div>
        </div>

        {downloadUrl && (
          <div className="mt-6 bg-surface-1 border border-signal-amber rounded p-6 text-center">
            <h3 className="font-bold font-display text-2xl text-ink-1 mb-1">Exercise package ready</h3>
            <p className="text-ink-3 text-sm font-mono mb-4">{downloadName}</p>
            <a
              href={downloadUrl}
              download={downloadName}
              className="inline-block bg-accent hover:bg-accent-hover text-accent-on font-semibold uppercase tracking-caps px-8 py-3 rounded text-base transition-colors"
            >
              Download package (.zip)
            </a>
          </div>
        )}

        {/* History Link */}
        <div className="mt-6 text-center">
          <a href="/history" className="text-accent hover:text-accent-hover underline text-sm">
            View past exercises →
          </a>
        </div>
      </div>
    </div>
  );
}
