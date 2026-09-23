'use client';

import React, { useEffect, useMemo, useReducer, useState } from 'react';
import Link from 'next/link';
import TreeView from '@/components/TreeView';
import {
  type CasesExport, type CriticalAction, type Vitals, PATHWAY_LABELS,
  fromExercise, gcsTotal, nextChange, pointAt,
} from '@/lib/controller';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://role2-builder-production.up.railway.app';

// --- Simulation state --------------------------------------------------------
// Sim time runs in seconds. The green clock pauses while the patient is on the
// red track, so rejoining green resumes where the team left it ("once they
// perform the correct intervention move to the green V/S and continue").

interface LogEntry { t: number; msg: string; kind: 'info' | 'red' | 'green' | 'action' | 'node' }
interface Sim {
  elapsed: number;
  running: boolean;
  speed: number;
  track: 'green' | 'red';
  redStart: number | null;
  redTotal: number;
  done: Record<string, number>;
  missed: Record<string, boolean>;
  reached: Record<string, string[]>;
  log: LogEntry[];
}

const initialSim = (): Sim => ({
  elapsed: 0, running: false, speed: 1, track: 'green', redStart: null, redTotal: 0,
  done: {}, missed: {}, reached: {}, log: [],
});

type Action =
  | { type: 'tick'; actions: CriticalAction[] }
  | { type: 'advance'; seconds: number; actions: CriticalAction[] }
  | { type: 'toggleRun' }
  | { type: 'speed'; speed: number }
  | { type: 'goRed'; reason: string }
  | { type: 'goGreen'; reason: string }
  | { type: 'done'; ca: CriticalAction; actions: CriticalAction[] }
  | { type: 'node'; legId: string; nodeId: string; label: string }
  | { type: 'load'; sim: Sim }
  | { type: 'reset' };

const greenSeconds = (s: Sim) =>
  s.elapsed - s.redTotal - (s.track === 'red' && s.redStart != null ? s.elapsed - s.redStart : 0);

function toRed(s: Sim, reason: string): Sim {
  if (s.track === 'red') return s;
  return { ...s, track: 'red', redStart: s.elapsed, log: [...s.log, { t: s.elapsed, msg: `RED — ${reason}`, kind: 'red' }] };
}

function toGreen(s: Sim, reason: string): Sim {
  if (s.track === 'green' || s.redStart == null) return s;
  return {
    ...s, track: 'green', redTotal: s.redTotal + (s.elapsed - s.redStart), redStart: null,
    log: [...s.log, { t: s.elapsed, msg: `GREEN — ${reason}`, kind: 'green' }],
  };
}

function checkWindows(s: Sim, actions: CriticalAction[]): Sim {
  let out = s;
  const gm = greenSeconds(out) / 60;
  for (const ca of actions) {
    if (ca.window_min == null || out.done[ca.id] !== undefined || out.missed[ca.id]) continue;
    if (gm >= ca.window_min) {
      out = { ...out, missed: { ...out.missed, [ca.id]: true } };
      out = toRed(out, `missed: ${ca.action}`);
    }
  }
  return out;
}

function reducer(s: Sim, a: Action): Sim {
  switch (a.type) {
    case 'tick':
      return s.running ? checkWindows({ ...s, elapsed: s.elapsed + s.speed }, a.actions) : s;
    case 'advance':
      return checkWindows({ ...s, elapsed: s.elapsed + a.seconds }, a.actions);
    case 'toggleRun':
      return { ...s, running: !s.running, log: [...s.log, { t: s.elapsed, msg: s.running ? 'Paused' : 'Running', kind: 'info' }] };
    case 'speed':
      return { ...s, speed: a.speed };
    case 'goRed':
      return toRed(s, a.reason);
    case 'goGreen':
      return toGreen(s, a.reason);
    case 'done': {
      if (s.done[a.ca.id] !== undefined) return s;
      let out: Sim = { ...s, done: { ...s.done, [a.ca.id]: s.elapsed },
        log: [...s.log, { t: s.elapsed, msg: `Performed: ${a.ca.action}`, kind: 'action' }] };
      const outstanding = a.actions.filter(c => out.missed[c.id] && out.done[c.id] === undefined);
      if (out.track === 'red' && outstanding.length === 0) out = toGreen(out, 'correct intervention performed');
      return out;
    }
    case 'node': {
      const cur = new Set(s.reached[a.legId] || []);
      const on = !cur.has(a.nodeId);
      if (on) cur.add(a.nodeId); else cur.delete(a.nodeId);
      return { ...s, reached: { ...s.reached, [a.legId]: [...cur] },
        log: on ? [...s.log, { t: s.elapsed, msg: `Tree: ${a.label}`, kind: 'node' }] : s.log };
    }
    case 'load':
      return { ...a.sim, running: false };
    case 'reset':
      return initialSim();
  }
}

const clock = (sec: number) => {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

function storageKey(ex: string, n: number) {
  return `r2b.controller.${ex}.${n}`;
}

// --- Page ----------------------------------------------------------------------

export default function ControllerPage() {
  const [data, setData] = useState<CasesExport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [caseIdx, setCaseIdx] = useState(0);
  const [legId, setLegId] = useState<string | null>(null);
  const [sim, dispatch] = useReducer(reducer, undefined, initialSim);
  const [showFindings, setShowFindings] = useState(false);

  // ?exercise=<id> loads a stored exercise; otherwise the user loads cases.json.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('exercise');
    if (!id) return;
    fetch(`${API_BASE}/exercises/${id}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`Exercise ${id} not found`))))
      .then(ex => setData(fromExercise(ex)))
      .catch(e => setError(e.message));
  }, []);

  const entry = data?.cases[caseIdx];
  const ctrl = entry?.case.controller;
  const focusLeg = ctrl?.legs.find(l => l.focus) || ctrl?.legs[0];
  const focusActions = useMemo(
    () => (ctrl?.critical_actions || []).filter(a => !focusLeg || a.leg_id === focusLeg.leg_id),
    [ctrl, focusLeg],
  );
  const leg = ctrl?.legs.find(l => l.leg_id === legId) || focusLeg;

  // Restore / persist per-case sim state (per-viewer convenience only).
  useEffect(() => {
    if (!data || !entry) return;
    setLegId(null);
    try {
      const raw = localStorage.getItem(storageKey(data.exercise, entry.case_num));
      dispatch(raw ? { type: 'load', sim: JSON.parse(raw) } : { type: 'reset' });
    } catch {
      dispatch({ type: 'reset' });
    }
  }, [data, entry]);
  useEffect(() => {
    if (!data || !entry) return;
    try { localStorage.setItem(storageKey(data.exercise, entry.case_num), JSON.stringify(sim)); } catch { /* storage unavailable */ }
  }, [sim, data, entry]);

  useEffect(() => {
    if (!sim.running) return;
    const h = setInterval(() => dispatch({ type: 'tick', actions: focusActions }), 1000);
    return () => clearInterval(h);
  }, [sim.running, focusActions]);

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    try {
      const parsed = JSON.parse(await f.text());
      if (parsed.format !== 'role2builder.cases.v1') throw new Error('Not a Role 2 Builder cases.json file');
      setData(parsed);
      setCaseIdx(0);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read file');
    }
  };

  const downloadLog = () => {
    if (!data || !entry) return;
    const blob = new Blob([JSON.stringify({
      exercise: data.exercise, case: entry.case_num, title: entry.case.meta?.title,
      reached: sim.reached, done: sim.done, missed: sim.missed, log: sim.log,
    }, null, 1)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${data.exercise}_case${entry.case_num}_controller_log.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const tracks = ctrl?.vitals_tracks || { green: [], red: [] };
  const gm = greenSeconds(sim) / 60;
  const rm = sim.redStart != null ? (tracks.red[0]?.t ?? 0) + (sim.elapsed - sim.redStart) / 60 : 0;
  const current: Vitals | null = sim.track === 'red' && tracks.red.length ? pointAt(tracks.red, rm) : pointAt(tracks.green, gm);
  const nxt = sim.track === 'red' ? nextChange(tracks.red, rm) : nextChange(tracks.green, gm);
  const nxtIn = nxt == null ? null : (nxt - (sim.track === 'red' ? rm : gm)) * 60;
  const trackColour = sim.track === 'red' ? 'border-signal-red text-signal-red' : 'border-signal-green text-signal-green';

  return (
    <div className="min-h-screen bg-surface-0 text-ink-1 p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold font-display tracking-display">Live controller</h1>
            <p className="text-ink-3 text-sm">{data ? data.exercise : 'Load a cases.json file from an exercise package, or open an exercise from History.'}</p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <label className="px-3 py-1.5 bg-surface-2 hover:bg-surface-3 border border-border-1 rounded cursor-pointer">
              Load cases.json
              <input type="file" accept="application/json,.json" className="hidden" onChange={e => onFile(e.target.files?.[0])} />
            </label>
            <Link href="/history" className="text-accent hover:text-accent-hover">History</Link>
            <Link href="/" className="text-accent hover:text-accent-hover">New exercise</Link>
          </div>
        </div>

        {error && <div className="bg-surface-2 border-l-4 border-signal-red rounded p-3 text-signal-red text-sm">{error}</div>}

        {data && (
          <select
            value={caseIdx}
            onChange={e => setCaseIdx(Number(e.target.value))}
            className="w-full bg-surface-1 border border-border-1 rounded px-3 py-2 text-sm"
          >
            {data.cases.map((c, i) => {
              const k = c.case.controller?.red_team?.counts || {};
              return (
                <option key={i} value={i}>
                  Case {c.case_num} · D{c.day ?? '?'} {c.arrival ?? ''} · {c.case.meta?.title} · {PATHWAY_LABELS[c.case.controller?.pathway || ''] || 'no controller layer'} · red team {k.high ?? 0}H/{k.medium ?? 0}M
                </option>
              );
            })}
          </select>
        )}

        {entry && !ctrl && (
          <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm text-ink-3">
            This case predates decision trees — regenerate the exercise to get a controller layer.
          </div>
        )}

        {entry && ctrl && (
          <>
            {/* Monitor + controls */}
            <div className="grid md:grid-cols-3 gap-4">
              <div className={`md:col-span-2 bg-surface-1 border-2 ${trackColour} rounded p-4`}>
                <div className="flex items-center justify-between mb-3">
                  <span className={`text-xs font-semibold uppercase tracking-caps ${trackColour.split(' ')[1]}`}>
                    {sim.track === 'red' ? 'Red track — deteriorating' : 'Green track'}
                  </span>
                  <span className="font-mono text-ink-3 text-xs">
                    {nxtIn != null ? `next vitals in ${clock(Math.max(0, nxtIn))}` : 'end of track'}
                  </span>
                </div>
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 font-mono">
                  {[
                    ['HR', current?.hr],
                    ['BP', current?.sbp != null ? `${current.sbp}/${current.dbp}` : '—'],
                    ['RR', current?.rr],
                    ['SpO2', current?.spo2],
                    ['Temp', current?.temp_f],
                    ['AVPU', current?.avpu],
                  ].map(([k, v]) => (
                    <div key={k as string}>
                      <div className="text-xs text-ink-3">{k}</div>
                      <div className="text-2xl md:text-3xl text-ink-1">{v ?? '—'}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-3 text-sm text-ink-2 font-mono">
                  GCS {gcsTotal(current) ?? '—'} (E{current?.gcs_e ?? '-'} V{current?.gcs_v ?? '-'} M{current?.gcs_m ?? '-'}) · Pupils {current?.pupils ?? '—'}
                  {current?.etco2 != null && ` · ETCO2 ${current.etco2}`}
                </div>
                {ctrl.controller_note && <p className="mt-3 text-xs italic text-ink-3">{ctrl.controller_note}</p>}
              </div>

              <div className="bg-surface-1 border border-border-1 rounded p-4 space-y-3">
                <div className="text-4xl font-mono text-center">{clock(sim.elapsed)}</div>
                <div className="flex gap-2">
                  <button onClick={() => dispatch({ type: 'toggleRun' })}
                    className="flex-1 px-3 py-2 rounded bg-accent hover:bg-accent-hover text-accent-on text-xs font-semibold uppercase tracking-caps">
                    {sim.running ? 'Pause' : 'Start'}
                  </button>
                  <button onClick={() => dispatch({ type: 'advance', seconds: 300, actions: focusActions })}
                    className="px-3 py-2 rounded bg-surface-2 hover:bg-surface-3 border border-border-1 text-xs">+5 min</button>
                  <select value={sim.speed} onChange={e => dispatch({ type: 'speed', speed: Number(e.target.value) })}
                    className="bg-surface-2 border border-border-1 rounded px-2 text-xs" aria-label="Speed">
                    {[1, 5, 10, 30].map(s => <option key={s} value={s}>{s}×</option>)}
                  </select>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => dispatch({ type: 'goRed', reason: 'controller call' })}
                    className="flex-1 px-3 py-1.5 rounded border border-signal-red text-signal-red text-xs">Go red</button>
                  <button onClick={() => dispatch({ type: 'goGreen', reason: 'controller call' })}
                    className="flex-1 px-3 py-1.5 rounded border border-signal-green text-signal-green text-xs">Go green</button>
                  <button onClick={() => { if (confirm('Reset this case?')) dispatch({ type: 'reset' }); }}
                    className="px-3 py-1.5 rounded bg-surface-2 border border-border-1 text-xs">Reset</button>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-1">Critical actions</p>
                  {focusActions.length === 0 && <p className="text-xs text-ink-3">None defined.</p>}
                  {focusActions.map(ca => {
                    const done = sim.done[ca.id] !== undefined;
                    const missed = sim.missed[ca.id];
                    const left = ca.window_min != null ? ca.window_min * 60 - greenSeconds(sim) : null;
                    return (
                      <label key={ca.id} className="flex items-start gap-2 py-1 text-sm">
                        <input type="checkbox" checked={done} disabled={done}
                          onChange={() => dispatch({ type: 'done', ca, actions: focusActions })} className="mt-1" />
                        <span className={missed && !done ? 'text-signal-red' : done ? 'text-signal-green' : ''}>
                          {ca.action}
                          <span className="block text-xs text-ink-3">
                            {done ? `done at ${clock(sim.done[ca.id])}` : missed ? `MISSED — ${ca.if_missed || 'red track'}` :
                              left != null ? `window ${clock(Math.max(0, left))}` : ''}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Legs */}
            <div className="bg-surface-1 border border-border-1 rounded p-4">
              <div className="flex flex-wrap gap-2 mb-3">
                {ctrl.legs.map(l => (
                  <button key={l.leg_id} onClick={() => setLegId(l.leg_id)}
                    className={`px-3 py-1 rounded text-xs border ${leg?.leg_id === l.leg_id ? 'bg-accent text-accent-on border-accent' : 'bg-surface-2 border-border-1 text-ink-2'}`}>
                    {l.title}{l.focus ? ' ★' : ''}
                  </button>
                ))}
              </div>
              {leg && (
                <div className="space-y-3">
                  {leg.handover && (leg.handover.summary || leg.handover.vitals) && (
                    <div className="text-sm bg-surface-2 rounded p-3">
                      <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-1">Turnover</p>
                      {leg.handover.vitals && (
                        <p className="font-mono">HR {leg.handover.vitals.hr ?? '—'} · BP {leg.handover.vitals.sbp ?? '—'}/{leg.handover.vitals.dbp ?? '—'} · RR {leg.handover.vitals.rr ?? '—'} · SpO2 {leg.handover.vitals.spo2 ?? '—'} · {leg.handover.vitals.avpu ?? ''}</p>
                      )}
                      {leg.handover.summary && <p className="text-ink-2 mt-1">{leg.handover.summary}</p>}
                      {!!leg.handover.meds?.length && (
                        <p className="text-ink-2 mt-1">Meds: {leg.handover.meds.map(m => `${m.drug} ${m.dose} ${m.route ?? ''} @ ${m.minutes_prior ?? '?'} min prior`).join('; ')}</p>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-ink-3">Click a box to mark the path the team took; it goes into the debrief log.</p>
                  <TreeView leg={leg} reached={new Set(sim.reached[leg.leg_id] || [])}
                    onToggle={nodeId => dispatch({ type: 'node', legId: leg.leg_id, nodeId,
                      label: leg.tree.nodes.find(n => n.id === nodeId)?.label || nodeId })} />
                  {!!leg.considerations?.length && (
                    <p className="text-sm"><span className="text-signal-red font-semibold">*Other important considerations: </span>{leg.considerations.join(' · ')}</p>
                  )}
                </div>
              )}
            </div>

            {/* Case detail + log */}
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm space-y-2">
                <p className="text-xs font-semibold uppercase tracking-caps text-ink-3">Case</p>
                <p><span className="text-ink-3">Care chain:</span> {ctrl.chain.nodes.map(n => n.name).join(' → ')}</p>
                {!!ctrl.chain.fragos.length && (
                  <p><span className="text-ink-3">FRAGOs in force:</span> {ctrl.chain.fragos.map(n => {
                    const f = data?.fragos.find(x => x.number === n);
                    return `${String(n).padStart(2, '0')} ${f?.title ?? ''}`;
                  }).join('; ')}</p>
                )}
                <p><span className="text-ink-3">Pathway:</span> {PATHWAY_LABELS[ctrl.pathway] || ctrl.pathway}</p>
                <p><span className="text-ink-3">Z-MIST:</span> {['mechanism', 'injuries', 'signs', 'treatment'].map(k => entry.case.zmist?.[k]).filter(Boolean).join(' / ')}</p>
                {ctrl.moulage && <p><span className="text-ink-3">Moulage:</span> {ctrl.moulage}</p>}
                {!!ctrl.critical_decisions?.length && (
                  <ul className="list-disc ml-5">{ctrl.critical_decisions.map((d, i) => <li key={i}>{d}</li>)}</ul>
                )}
                {!!ctrl.wounds?.length && (
                  <ul className="list-disc ml-5 text-ink-2">{ctrl.wounds.map(w => (
                    <li key={w.id}>{w.side} {w.region} ({w.surface}): {w.type} — {w.intervention}{w.effective === false ? ' (ineffective)' : ''}</li>
                  ))}</ul>
                )}
                <button onClick={() => setShowFindings(v => !v)} className="text-accent hover:text-accent-hover text-xs">
                  {showFindings ? 'Hide' : 'Show'} red-team findings ({ctrl.red_team?.open.length ?? 0})
                </button>
                {showFindings && (
                  <ul className="space-y-1 text-xs">
                    {(ctrl.red_team?.open || []).map((f, i) => (
                      <li key={i} className={f.severity === 'high' ? 'text-signal-red' : f.severity === 'medium' ? 'text-signal-amber' : 'text-ink-3'}>
                        [{f.severity}] {f.issue} <span className="text-ink-3">Fix: {f.fix}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold uppercase tracking-caps text-ink-3">Event log</p>
                  <button onClick={downloadLog} className="text-accent hover:text-accent-hover text-xs">Download debrief log</button>
                </div>
                <ul className="font-mono text-xs space-y-0.5 max-h-72 overflow-y-auto">
                  {sim.log.length === 0 && <li className="text-ink-3">Nothing yet.</li>}
                  {sim.log.map((l, i) => (
                    <li key={i} className={l.kind === 'red' ? 'text-signal-red' : l.kind === 'green' ? 'text-signal-green' : 'text-ink-2'}>
                      {clock(l.t)} {l.msg}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
