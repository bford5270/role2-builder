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
        if (job.progress.includes('Road to War')) setProgressPct(88);
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

  // MASCAL is additive: it adds one wave and its patient count to the day.
  const dayPatients = (d: DayConfig) => d.total_patients + (d.mascal && d.mascal_patients ? d.mascal_patients : 0);
  const dayWaves = (d: DayConfig) => d.total_waves + (d.mascal ? 1 : 0);
  const getTotalCasualties = () => days.reduce((sum, d) => sum + dayPatients(d), 0);

  // Shared style objects
  const labelStyle: React.CSSProperties = {
    fontFamily: 'var(--font-body)',
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.10em',
    textTransform: 'uppercase',
    color: 'var(--ink-3)',
    display: 'block',
    marginBottom: 4,
  };

  const inputStyle: React.CSSProperties = {
    background: 'var(--surface-2)',
    border: '1px solid var(--border-2)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--ink-1)',
    fontFamily: 'var(--font-body)',
    fontSize: 13,
    padding: '6px 10px',
    width: '100%',
    boxSizing: 'border-box',
  };

  const cardStyle: React.CSSProperties = {
    background: 'var(--surface-1)',
    border: '1px solid var(--border-1)',
    borderRadius: 'var(--radius-md)',
    padding: 20,
  };

  if (!config) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--surface-0)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--ink-1)', marginBottom: 16 }}>
            No exercise configuration found
          </h2>
          <a href="/" style={{ color: 'var(--signal-amber)', fontFamily: 'var(--font-body)', fontSize: 14, textDecoration: 'none' }}>
            Return to Setup
          </a>
        </div>
      </div>
    );
  }

  const isDisabled = generating || days.some(d => d.mascal && !d.mascal_etiology);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--surface-0)', padding: '24px' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        {/* Page header */}
        <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 24, color: 'var(--ink-1)', letterSpacing: '-0.01em', margin: 0 }}>
              {config.exercise_name}
            </h1>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-2)', marginTop: 4 }}>
              {config.duration} Days &nbsp;|&nbsp; {config.environment} &nbsp;|&nbsp; {config.region} &nbsp;|&nbsp; {config.threat_level}
            </p>
          </div>
          <a href="/" style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-3)', textDecoration: 'none' }}>
            Back to Setup
          </a>
        </div>

        {/* Summary bar */}
        <div style={{ ...cardStyle, marginBottom: 24, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, textAlign: 'center' }}>
          {[
            { value: config.duration, label: 'Days' },
            { value: getTotalCasualties(), label: 'Total Casualties' },
            { value: days.filter(d => d.mascal).length, label: 'MASCAL Events' },
            { value: days.filter(d => d.cbrn).length, label: 'CBRN Drills' },
          ].map(({ value, label }) => (
            <div key={label}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 700, color: 'var(--ink-1)' }}>{value}</div>
              <div style={labelStyle as React.CSSProperties}>{label}</div>
            </div>
          ))}
        </div>

        {/* Day cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 32 }}>
          {days.map((day, idx) => (
            <div key={idx} style={cardStyle}>
              {/* Day header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--ink-1)', margin: 0, letterSpacing: '-0.01em' }}>
                  Day {day.day_number}
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 400, fontSize: 12, color: 'var(--ink-3)', marginLeft: 10 }}>
                    {dayPatients(day)} patients · {dayWaves(day)} waves{day.mascal && day.mascal_patients ? ' (incl. MASCAL)' : ''}
                  </span>
                </h3>
                {idx < days.length - 1 && (
                  <button
                    onClick={() => copyDayConfig(idx)}
                    style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--ink-3)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                  >
                    Copy to remaining days
                  </button>
                )}
              </div>

              {/* Main fields row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16 }}>
                <div>
                  <label style={labelStyle}>Tactical Setting</label>
                  <select
                    value={day.tactical_setting}
                    onChange={(e) => updateDay(idx, 'tactical_setting', e.target.value)}
                    style={inputStyle}
                  >
                    {TACTICAL_SETTINGS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>

                <div>
                  <label style={labelStyle}>Routine Patients</label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={day.total_patients}
                    onChange={(e) => updateDay(idx, 'total_patients', parseInt(e.target.value) || 1)}
                    style={inputStyle}
                  />
                </div>

                <div>
                  <label style={labelStyle}>Routine Waves</label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={day.total_waves}
                    onChange={(e) => updateDay(idx, 'total_waves', parseInt(e.target.value) || 1)}
                    style={inputStyle}
                  />
                </div>

                {/* Night Ops toggle */}
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 10 }}>
                    <input
                      type="checkbox"
                      checked={day.night_ops}
                      onChange={(e) => updateDay(idx, 'night_ops', e.target.checked)}
                      style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
                    />
                    {/* Toggle track */}
                    <div
                      style={{
                        width: 40,
                        height: 20,
                        borderRadius: 10,
                        background: day.night_ops ? 'var(--signal-amber)' : 'var(--surface-3)',
                        position: 'relative',
                        transition: 'background 0.2s',
                        flexShrink: 0,
                      }}
                    >
                      <div
                        style={{
                          width: 16,
                          height: 16,
                          borderRadius: '50%',
                          background: 'var(--ink-1)',
                          position: 'absolute',
                          top: 2,
                          left: day.night_ops ? 22 : 2,
                          transition: 'left 0.2s',
                        }}
                      />
                    </div>
                    <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-2)' }}>
                      Night Ops (1900–0700)
                    </span>
                  </label>
                </div>
              </div>

              {/* Stressors */}
              <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border-1)' }}>
                <div style={{ ...labelStyle, marginBottom: 10 } as React.CSSProperties}>Operational Stressors</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>

                  {/* MASCAL */}
                  <div style={{ background: 'var(--surface-2)', borderRadius: 'var(--radius-md)', padding: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 10, marginBottom: day.mascal ? 10 : 0 }}>
                      <input
                        type="checkbox"
                        checked={day.mascal}
                        onChange={(e) => updateDay(idx, 'mascal', e.target.checked)}
                        style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
                      />
                      <div
                        style={{
                          width: 40,
                          height: 20,
                          borderRadius: 10,
                          background: day.mascal ? 'var(--signal-red)' : 'var(--surface-3)',
                          position: 'relative',
                          transition: 'background 0.2s',
                          flexShrink: 0,
                        }}
                      >
                        <div
                          style={{
                            width: 16,
                            height: 16,
                            borderRadius: '50%',
                            background: 'var(--ink-1)',
                            position: 'absolute',
                            top: 2,
                            left: day.mascal ? 22 : 2,
                            transition: 'left 0.2s',
                          }}
                        />
                      </div>
                      <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600, color: 'var(--signal-red)' }}>
                        MASCAL
                      </span>
                    </label>
                    {day.mascal && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <select
                          value={day.mascal_etiology || ''}
                          onChange={(e) => updateDay(idx, 'mascal_etiology', e.target.value)}
                          style={{ ...inputStyle, fontSize: 12 }}
                        >
                          <option value="">Select Etiology</option>
                          {MASCAL_ETIOLOGIES.map(e => <option key={e} value={e}>{e}</option>)}
                        </select>
                        <input
                          type="number"
                          placeholder="MASCAL patient count"
                          min="3"
                          max="20"
                          value={day.mascal_patients || ''}
                          onChange={(e) => updateDay(idx, 'mascal_patients', parseInt(e.target.value) || null)}
                          style={{ ...inputStyle, fontSize: 12 }}
                        />
                        {day.mascal_patients ? (
                          <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--ink-3)', margin: 0 }}>
                            +1 wave · +{day.mascal_patients} patients added to Day {day.day_number} (now {dayPatients(day)} across {dayWaves(day)} waves)
                          </p>
                        ) : null}
                      </div>
                    )}
                  </div>

                  {/* CBRN */}
                  <div style={{ background: 'var(--surface-2)', borderRadius: 'var(--radius-md)', padding: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 10 }}>
                      <input
                        type="checkbox"
                        checked={day.cbrn}
                        onChange={(e) => updateDay(idx, 'cbrn', e.target.checked)}
                        style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
                      />
                      <div
                        style={{
                          width: 40,
                          height: 20,
                          borderRadius: 10,
                          background: day.cbrn ? 'var(--signal-amber)' : 'var(--surface-3)',
                          position: 'relative',
                          transition: 'background 0.2s',
                          flexShrink: 0,
                        }}
                      >
                        <div
                          style={{
                            width: 16,
                            height: 16,
                            borderRadius: '50%',
                            background: 'var(--ink-1)',
                            position: 'absolute',
                            top: 2,
                            left: day.cbrn ? 22 : 2,
                            transition: 'left 0.2s',
                          }}
                        />
                      </div>
                      <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600, color: 'var(--signal-amber)' }}>
                        CBRN Drill
                      </span>
                    </label>
                    {day.cbrn && (
                      <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--ink-3)', marginTop: 8, marginBottom: 0 }}>
                        1-hour drill, all clinical ops paused
                      </p>
                    )}
                  </div>

                  {/* Detainee Ops */}
                  <div style={{ background: 'var(--surface-2)', borderRadius: 'var(--radius-md)', padding: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 10 }}>
                      <input
                        type="checkbox"
                        checked={day.detainee_ops}
                        onChange={(e) => updateDay(idx, 'detainee_ops', e.target.checked)}
                        style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
                      />
                      <div
                        style={{
                          width: 40,
                          height: 20,
                          borderRadius: 10,
                          background: day.detainee_ops ? 'var(--signal-amber)' : 'var(--surface-3)',
                          position: 'relative',
                          transition: 'background 0.2s',
                          flexShrink: 0,
                        }}
                      >
                        <div
                          style={{
                            width: 16,
                            height: 16,
                            borderRadius: '50%',
                            background: 'var(--ink-1)',
                            position: 'absolute',
                            top: 2,
                            left: day.detainee_ops ? 22 : 2,
                            transition: 'left 0.2s',
                          }}
                        />
                      </div>
                      <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600, color: 'var(--ink-2)' }}>
                        Detainee Ops
                      </span>
                    </label>
                    {day.detainee_ops && (
                      <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--ink-3)', marginTop: 8, marginBottom: 0 }}>
                        Includes detainee medical scenarios
                      </p>
                    )}
                  </div>

                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div style={{ background: 'rgba(179,58,58,0.12)', border: '1px solid var(--signal-red)', borderRadius: 'var(--radius-md)', padding: '12px 16px', marginBottom: 20 }}>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--signal-red)', margin: 0 }}>{error}</p>
          </div>
        )}

        {/* Progress */}
        {progress && (
          <div style={{ ...cardStyle, marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              {generating && (
                <svg
                  style={{ width: 18, height: 18, flexShrink: 0, animation: 'spin 1s linear infinite', color: 'var(--signal-amber)' }}
                  viewBox="0 0 24 24"
                >
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity="0.25" />
                  <path fill="currentColor" opacity="0.75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-2)', margin: 0 }}>{progress}</p>
            </div>
            <div style={{ width: '100%', background: 'var(--surface-2)', borderRadius: 4, height: 6, overflow: 'hidden' }}>
              <div
                style={{
                  background: 'var(--signal-amber)',
                  height: '100%',
                  width: `${progressPct}%`,
                  borderRadius: 4,
                  transition: 'width 0.5s ease',
                }}
              />
            </div>
          </div>
        )}

        {/* Generate button */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <button
            onClick={handleGenerate}
            disabled={isDisabled}
            style={{
              background: isDisabled ? 'var(--surface-3)' : 'var(--accent)',
              color: isDisabled ? 'var(--ink-4)' : 'var(--accent-on)',
              fontFamily: 'var(--font-body)',
              fontWeight: 600,
              fontSize: 15,
              border: 0,
              borderRadius: 'var(--radius-md)',
              padding: '14px 40px',
              cursor: isDisabled ? 'not-allowed' : 'pointer',
              letterSpacing: '0.02em',
              transition: 'background 0.2s',
            }}
          >
            {generating ? 'Generating Exercise Package...' : 'Generate All Documents'}
          </button>
          {days.some(d => d.mascal && !d.mascal_etiology) && (
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--signal-red)', margin: 0 }}>
              Select a MASCAL etiology for all MASCAL days before generating.
            </p>
          )}
        </div>

        {/* Package contents */}
        <div style={{ ...cardStyle, marginTop: 32 }}>
          <div style={{ ...labelStyle, marginBottom: 12 } as React.CSSProperties}>Package Contents</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8 }}>
            {[
              { name: 'MSEL.xlsx' },
              { name: 'WARNO.docx' },
              { name: 'Annex_Q.docx' },
              { name: 'MEDROE.docx' },
              { name: 'Case_Book.docx' },
              { name: 'Road_to_War_Prompt.docx' },
            ].map(({ name }) => (
              <div
                key={name}
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border-1)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '10px 12px',
                  textAlign: 'center',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--ink-2)',
                }}
              >
                {name}
              </div>
            ))}
          </div>
        </div>

        {/* Download ready */}
        {downloadUrl && (
          <div
            style={{
              marginTop: 24,
              border: '1px solid var(--signal-green)',
              background: 'rgba(107,127,79,0.10)',
              borderRadius: 'var(--radius-md)',
              padding: '28px 24px',
              textAlign: 'center',
            }}
          >
            <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20, color: 'var(--ink-1)', margin: '0 0 6px', letterSpacing: '-0.01em' }}>
              Exercise Package Ready
            </h3>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-2)', margin: '0 0 20px' }}>{downloadName}</p>
            <a
              href={downloadUrl}
              download={downloadName}
              style={{
                display: 'inline-block',
                background: 'var(--accent)',
                color: 'var(--accent-on)',
                fontFamily: 'var(--font-body)',
                fontWeight: 600,
                fontSize: 15,
                padding: '12px 36px',
                borderRadius: 'var(--radius-md)',
                textDecoration: 'none',
                letterSpacing: '0.02em',
              }}
            >
              Download Package (.zip)
            </a>
          </div>
        )}

        {/* History link */}
        <div style={{ marginTop: 24, textAlign: 'center' }}>
          <a
            href="/history"
            style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-3)', textDecoration: 'underline' }}
          >
            View Past Exercises
          </a>
        </div>

      </div>

      {/* Keyframe animation for spinner (inline since no globals change allowed) */}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
