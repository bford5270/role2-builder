'use client';

import React, { useEffect, useRef, useState } from 'react';

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
const POLL_INTERVAL_MS = 2500;

type JobStatus = 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';

interface JobStatusBody {
  job_id: string;
  status: JobStatus;
  current_phase: string;
  total_cases: number;
  completed_cases: number;
  progress: number;
  errors_count: number;
  exercise_id: number | null;
  error_message: string | null;
  generation_summary: {
    total_requested: number;
    total_returned: number;
    total_fallback: number;
    errors: unknown[];
  } | null;
  created_at: string;
  updated_at: string;
}

const PHASE_LABELS: Record<string, string> = {
  queued: 'Queued — waiting for an open worker slot',
  planning: 'Planning casualty mix',
  generating_cases: 'Generating cases',
  generating_docs: 'Generating WARNO / Annex Q / MEDROE',
  packaging: 'Packaging exercise ZIP',
  complete: 'Complete',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export default function TacticalScenarioPage() {
  const [config, setConfig] = useState<ExerciseConfig | null>(null);
  const [days, setDays] = useState<DayConfig[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string>('');
  const [job, setJob] = useState<JobStatusBody | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  };

  // Cleanup on unmount.
  useEffect(() => () => stopPolling(), []);

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

  const downloadJobZip = async (jobId: string, exerciseName: string) => {
    const response = await fetch(`${API_BASE}/jobs/${jobId}/download`);
    if (!response.ok) {
      throw new Error(`Download failed (${response.status})`);
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${exerciseName}_Package.zip`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  const pollJob = async (jobId: string, exerciseName: string) => {
    try {
      const r = await fetch(`${API_BASE}/jobs/${jobId}`);
      if (!r.ok) {
        throw new Error(`Status check failed (${r.status})`);
      }
      const body: JobStatusBody = await r.json();
      setJob(body);

      if (body.status === 'complete') {
        stopPolling();
        setProgress('Downloading package...');
        await downloadJobZip(jobId, exerciseName);
        setProgress('Complete. Check your downloads folder.');
        setGenerating(false);
      } else if (body.status === 'failed') {
        stopPolling();
        setError(body.error_message || 'Generation failed');
        setProgress('');
        setGenerating(false);
      } else if (body.status === 'cancelled') {
        stopPolling();
        setProgress('Cancelled.');
        setGenerating(false);
      }
    } catch (err) {
      stopPolling();
      setError(err instanceof Error ? err.message : 'Polling failed');
      setGenerating(false);
    }
  };

  const handleGenerate = async () => {
    if (!config) return;

    setGenerating(true);
    setError(null);
    setJob(null);
    setProgress('Submitting exercise configuration...');

    try {
      const fullConfig: ExerciseConfig = { ...config, days: days };
      const response = await fetch(`${API_BASE}/jobs/generate-exercise`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fullConfig),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Submission failed');
      }

      const queued = await response.json();
      const jobId: string = queued.job_id;
      setJob({
        job_id: jobId,
        status: queued.status,
        current_phase: queued.current_phase,
        total_cases: queued.total_cases,
        completed_cases: 0,
        progress: 0,
        errors_count: 0,
        exercise_id: null,
        error_message: null,
        generation_summary: null,
        created_at: queued.created_at,
        updated_at: queued.created_at,
      });
      setProgress('');

      // Kick off polling.
      stopPolling();
      pollJob(jobId, config.exercise_name);
      pollTimer.current = setInterval(() => pollJob(jobId, config.exercise_name), POLL_INTERVAL_MS);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setProgress('');
      setGenerating(false);
    }
  };

  const handleCancel = async () => {
    if (!job) return;
    try {
      const r = await fetch(`${API_BASE}/jobs/${job.job_id}/cancel`, { method: 'POST' });
      if (!r.ok && r.status !== 409) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || 'Cancel failed');
      }
      // Polling will pick up the new status.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cancel failed');
    }
  };

  const getTotalCasualties = () => days.reduce((sum, d) => sum + d.total_patients, 0);

  if (!config) {
    return (
      <div className="min-h-screen bg-stone-900 text-amber-100 p-8 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-xl mb-4">No exercise configuration found</h2>
          <a href="/" className="text-amber-400 hover:text-amber-300 underline">← Return to Setup</a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-stone-900 text-amber-100 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-amber-400">{config.exercise_name}</h1>
            <p className="text-stone-400">{config.duration} Days | {config.environment} | {config.region} | {config.threat_level}</p>
          </div>
          <a href="/" className="text-amber-400 hover:text-amber-300 text-sm">← Back to Setup</a>
        </div>

        <div className="bg-stone-800 border border-stone-700 rounded-lg p-4 mb-6 grid grid-cols-4 gap-4 text-center">
          <div><div className="text-2xl font-bold text-amber-400">{config.duration}</div><div className="text-xs text-stone-400">Days</div></div>
          <div><div className="text-2xl font-bold text-amber-400">{getTotalCasualties()}</div><div className="text-xs text-stone-400">Total Casualties</div></div>
          <div><div className="text-2xl font-bold text-amber-400">{days.filter(d => d.mascal).length}</div><div className="text-xs text-stone-400">MASCAL Events</div></div>
          <div><div className="text-2xl font-bold text-amber-400">{days.filter(d => d.cbrn).length}</div><div className="text-xs text-stone-400">CBRN Drills</div></div>
        </div>

        <div className="space-y-4 mb-8">
          {days.map((day, idx) => (
            <div key={idx} className="bg-stone-800 border border-stone-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-amber-400">Day {day.day_number}</h3>
                {idx < days.length - 1 && (
                  <button onClick={() => copyDayConfig(idx)} className="text-xs text-stone-400 hover:text-amber-400">Copy to remaining days →</button>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div>
                  <label className="block text-xs text-stone-400 mb-1">Tactical Setting</label>
                  <select value={day.tactical_setting} onChange={(e) => updateDay(idx, 'tactical_setting', e.target.value)} className="w-full bg-stone-700 border border-stone-600 rounded px-3 py-2 text-sm">
                    {TACTICAL_SETTINGS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-stone-400 mb-1">Total Patients</label>
                  <input type="number" min="1" max="50" value={day.total_patients} onChange={(e) => updateDay(idx, 'total_patients', parseInt(e.target.value) || 1)} className="w-full bg-stone-700 border border-stone-600 rounded px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-xs text-stone-400 mb-1">Number of Waves</label>
                  <input type="number" min="1" max="10" value={day.total_waves} onChange={(e) => updateDay(idx, 'total_waves', parseInt(e.target.value) || 1)} className="w-full bg-stone-700 border border-stone-600 rounded px-3 py-2 text-sm" />
                </div>
                <div className="flex items-center">
                  <label className="flex items-center cursor-pointer">
                    <input type="checkbox" checked={day.night_ops} onChange={(e) => updateDay(idx, 'night_ops', e.target.checked)} className="sr-only" />
                    <div className={`w-10 h-5 rounded-full transition-colors ${day.night_ops ? 'bg-amber-600' : 'bg-stone-600'}`}>
                      <div className={`w-4 h-4 rounded-full bg-white mt-0.5 transition-transform ${day.night_ops ? 'translate-x-5' : 'translate-x-0.5'}`} />
                    </div>
                    <span className="ml-2 text-sm">Night Ops (1900-0700)</span>
                  </label>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-stone-700">
                <div className="text-xs text-stone-400 mb-2">Operational Stressors</div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-stone-750 rounded p-3">
                    <label className="flex items-center cursor-pointer mb-2">
                      <input type="checkbox" checked={day.mascal} onChange={(e) => updateDay(idx, 'mascal', e.target.checked)} className="sr-only" />
                      <div className={`w-10 h-5 rounded-full transition-colors ${day.mascal ? 'bg-red-600' : 'bg-stone-600'}`}>
                        <div className={`w-4 h-4 rounded-full bg-white mt-0.5 transition-transform ${day.mascal ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </div>
                      <span className="ml-2 text-sm font-medium text-red-400">MASCAL</span>
                    </label>
                    {day.mascal && (
                      <div className="space-y-2 mt-2">
                        <select value={day.mascal_etiology || ''} onChange={(e) => updateDay(idx, 'mascal_etiology', e.target.value)} className="w-full bg-stone-700 border border-stone-600 rounded px-2 py-1 text-xs">
                          <option value="">Select Etiology</option>
                          {MASCAL_ETIOLOGIES.map(e => <option key={e} value={e}>{e}</option>)}
                        </select>
                        <input type="number" placeholder="MASCAL patients" min="3" max="20" value={day.mascal_patients || ''} onChange={(e) => updateDay(idx, 'mascal_patients', parseInt(e.target.value) || null)} className="w-full bg-stone-700 border border-stone-600 rounded px-2 py-1 text-xs" />
                      </div>
                    )}
                  </div>
                  <div className="bg-stone-750 rounded p-3">
                    <label className="flex items-center cursor-pointer">
                      <input type="checkbox" checked={day.cbrn} onChange={(e) => updateDay(idx, 'cbrn', e.target.checked)} className="sr-only" />
                      <div className={`w-10 h-5 rounded-full transition-colors ${day.cbrn ? 'bg-yellow-600' : 'bg-stone-600'}`}>
                        <div className={`w-4 h-4 rounded-full bg-white mt-0.5 transition-transform ${day.cbrn ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </div>
                      <span className="ml-2 text-sm font-medium text-yellow-400">CBRN Drill</span>
                    </label>
                    {day.cbrn && <p className="text-xs text-stone-400 mt-2">1-hour drill, all clinical ops paused</p>}
                  </div>
                  <div className="bg-stone-750 rounded p-3">
                    <label className="flex items-center cursor-pointer">
                      <input type="checkbox" checked={day.detainee_ops} onChange={(e) => updateDay(idx, 'detainee_ops', e.target.checked)} className="sr-only" />
                      <div className={`w-10 h-5 rounded-full transition-colors ${day.detainee_ops ? 'bg-blue-600' : 'bg-stone-600'}`}>
                        <div className={`w-4 h-4 rounded-full bg-white mt-0.5 transition-transform ${day.detainee_ops ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </div>
                      <span className="ml-2 text-sm font-medium text-blue-400">Detainee Ops</span>
                    </label>
                    {day.detainee_ops && <p className="text-xs text-stone-400 mt-2">Includes detainee medical scenarios</p>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {error && <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 mb-6"><p className="text-red-300">{error}</p></div>}

        {(job || progress) && (
          <div className="bg-stone-800 border border-amber-700 rounded-lg p-4 mb-6">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center">
                {generating && (
                  <svg className="animate-spin h-5 w-5 mr-3 text-amber-400" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                )}
                <p className="text-amber-300">
                  {job ? (PHASE_LABELS[job.current_phase] || job.current_phase) : progress}
                </p>
              </div>
              {job && (job.status === 'queued' || job.status === 'running') && (
                <button
                  onClick={handleCancel}
                  className="text-xs px-3 py-1 rounded border border-red-500 text-red-300 hover:bg-red-900/40"
                >
                  Cancel
                </button>
              )}
            </div>

            {job && job.total_cases > 0 && (
              <>
                <div className="w-full h-2 bg-stone-700 rounded overflow-hidden">
                  <div
                    className="h-full bg-amber-500 transition-all"
                    style={{ width: `${Math.round((job.progress || 0) * 100)}%` }}
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-stone-400">
                  <span>{job.completed_cases} / {job.total_cases} cases</span>
                  <span>Status: {job.status}</span>
                </div>
              </>
            )}

            {job && job.errors_count > 0 && (
              <div className="mt-3 text-xs text-yellow-300">
                ⚠ {job.errors_count} case{job.errors_count === 1 ? '' : 's'} fell back to a template after retries.
                The package still ships, but the generation_summary.json file inside the ZIP lists the failures.
              </div>
            )}

            {job && job.status === 'failed' && job.error_message && (
              <div className="mt-3 text-xs text-red-300">{job.error_message}</div>
            )}
          </div>
        )}

        <div className="flex justify-center">
          <button onClick={handleGenerate} disabled={generating || days.some(d => d.mascal && !d.mascal_etiology)} className={`px-8 py-4 rounded-lg font-bold text-lg transition-all ${generating || days.some(d => d.mascal && !d.mascal_etiology) ? 'bg-stone-700 text-stone-500 cursor-not-allowed' : 'bg-amber-600 hover:bg-amber-500 text-stone-900 shadow-lg hover:shadow-amber-600/25'}`}>
            {generating ? 'Generating Exercise Package...' : 'Generate All Documents'}
          </button>
        </div>

        {days.some(d => d.mascal && !d.mascal_etiology) && <p className="text-center text-red-400 text-sm mt-2">Please select a MASCAL etiology for all MASCAL days</p>}

        <div className="mt-8 bg-stone-800 border border-stone-700 rounded-lg p-4">
          <h3 className="text-amber-400 font-semibold mb-3">Package Contents</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-sm">
            <div className="bg-stone-700 rounded p-2 text-center"><div className="text-lg mb-1">📊</div><div>MSEL.xlsx</div></div>
            <div className="bg-stone-700 rounded p-2 text-center"><div className="text-lg mb-1">📄</div><div>WARNO.docx</div></div>
            <div className="bg-stone-700 rounded p-2 text-center"><div className="text-lg mb-1">🏥</div><div>Annex_Q.docx</div></div>
            <div className="bg-stone-700 rounded p-2 text-center"><div className="text-lg mb-1">⚖️</div><div>MEDROE.docx</div></div>
            <div className="bg-stone-700 rounded p-2 text-center"><div className="text-lg mb-1">📚</div><div>Case_Book.docx</div></div>
          </div>
        </div>

        {/* History Link */}
        <div className="mt-6 text-center">
          <a href="/history" className="text-amber-400 hover:text-amber-300 underline text-sm">
            View Past Exercises →
          </a>
        </div>
      </div>
    </div>
  );
}
