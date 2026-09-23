'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import TreeView from '@/components/TreeView';
import { type CaseRecord, type Finding, type Vitals, PATHWAY_LABELS } from '@/lib/controller';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://role2-builder-production.up.railway.app';

interface CaseRow {
  index: number; case_num: number; title?: string; zap?: string; pathway?: string; day?: number; arrival?: string;
  red_team?: Record<string, number>; has_controller: boolean; open_comments: number;
  status: string; reviewer?: string; decided_at?: string;
}
interface Comment { id: number; target: string; author: string; body: string; severity: string; resolved: boolean; created_at?: string }
interface Detail {
  exercise: { id: number; name: string }; index: number; case: CaseRecord;
  review: { status: string; reviewer?: string; note?: string; decided_at?: string }; comments: Comment[];
}

const STATUS_STYLE: Record<string, string> = {
  auto_checked: 'bg-surface-3 text-ink-2',
  in_review: 'bg-signal-blue/20 text-signal-blue',
  changes_requested: 'bg-signal-amber/20 text-signal-amber',
  approved: 'bg-signal-green/20 text-signal-green',
};
const STATUS_LABEL: Record<string, string> = {
  auto_checked: 'Auto-checked', in_review: 'In review', changes_requested: 'Changes requested', approved: 'Approved',
};

function Chip({ status }: { status: string }) {
  return <span className={`px-2 py-0.5 rounded text-xs ${STATUS_STYLE[status] || ''}`}>{STATUS_LABEL[status] || status}</span>;
}

const loadName = () => { try { return localStorage.getItem('r2b.reviewer') || ''; } catch { return ''; } };
const saveName = (n: string) => { try { localStorage.setItem('r2b.reviewer', n); } catch { /* unavailable */ } };

export default function ReviewPage() {
  const [exerciseId, setExerciseId] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [rows, setRows] = useState<CaseRow[]>([]);
  const [exName, setExName] = useState('');
  const [sel, setSel] = useState<number | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [legId, setLegId] = useState<string | null>(null);
  const [target, setTarget] = useState('general');
  const [severity, setSeverity] = useState('medium');
  const [body, setBody] = useState('');
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState('');
  const [editSummary, setEditSummary] = useState('');
  const [decision, setDecision] = useState('approved');
  const [note, setNote] = useState('');
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setExerciseId(new URLSearchParams(window.location.search).get('exercise'));
    setName(loadName());
    fetch(`${API_BASE}/reviews/status`).then(r => r.json()).then(d => setEnabled(!!d.enabled)).catch(() => setEnabled(false));
  }, []);

  const loadOverview = useCallback(async () => {
    if (!exerciseId) return;
    const r = await fetch(`${API_BASE}/exercises/${exerciseId}/review`);
    if (!r.ok) { setError((await r.json().catch(() => ({}))).detail || 'Could not load review'); return; }
    const d = await r.json();
    setRows(d.cases);
    setExName(d.exercise.name);
  }, [exerciseId]);

  const loadDetail = useCallback(async (idx: number) => {
    const r = await fetch(`${API_BASE}/exercises/${exerciseId}/review/${idx}`);
    if (!r.ok) { setError('Could not load case'); return; }
    const d: Detail = await r.json();
    setDetail(d);
    setEditText(JSON.stringify(d.case.controller ?? {}, null, 2));
  }, [exerciseId]);

  useEffect(() => { if (enabled) loadOverview(); }, [enabled, loadOverview]);
  useEffect(() => { if (sel != null) { setLegId(null); setTarget('general'); setEditing(false); loadDetail(sel); } }, [sel, loadDetail]);

  const call = async (url: string, method: string, payload: unknown) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE}${url}`, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Request failed');
      if (sel != null) await loadDetail(sel);
      await loadOverview();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const requireName = () => {
    if (!name.trim()) { setError('Enter your name (and specialty) first.'); return false; }
    saveName(name.trim());
    return true;
  };

  const addComment = async () => {
    if (!requireName() || !body.trim() || sel == null) return;
    if (await call(`/exercises/${exerciseId}/review/${sel}/comments`, 'POST', { author: name.trim(), target, body, severity })) setBody('');
  };

  const saveEdit = async () => {
    if (!requireName() || sel == null) return;
    let parsed;
    try { parsed = JSON.parse(editText); } catch { setError('Controller JSON is not valid JSON.'); return; }
    if (await call(`/exercises/${exerciseId}/review/${sel}/controller`, 'PUT', { author: name.trim(), controller: parsed, summary: editSummary })) {
      setEditing(false);
      setEditSummary('');
    }
  };

  const decide = async () => {
    if (!requireName() || sel == null) return;
    await call(`/exercises/${exerciseId}/review/${sel}/decision`, 'POST', { reviewer: name.trim(), status: decision, note, acknowledge_findings: ack });
  };

  const ctrl = detail?.case.controller;
  const leg = ctrl?.legs.find(l => l.leg_id === legId) || ctrl?.legs.find(l => l.focus) || ctrl?.legs[0];

  return (
    <div className="min-h-screen bg-surface-0 text-ink-1 p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold font-display tracking-display">Expert review</h1>
            <p className="text-ink-3 text-sm">{exName || 'Red-teamed cases awaiting expert sign-off'}</p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <input value={name} onChange={e => setName(e.target.value)} onBlur={() => name.trim() && saveName(name.trim())}
              placeholder="Your name / specialty" className="bg-surface-1 border border-border-1 rounded px-3 py-1.5 w-56" />
            <Link href="/library" className="text-accent hover:text-accent-hover">Library</Link>
            <Link href="/history" className="text-accent hover:text-accent-hover">History</Link>
          </div>
        </div>

        {enabled === false && (
          <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm text-ink-2">
            Review storage isn&apos;t configured on this server yet. Until it is, use the sign-off block in the Controller Packet and the
            Red Team sheet in the Controller Vitals workbook for offline review.
          </div>
        )}
        {enabled && !exerciseId && (
          <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm text-ink-2">
            Open an exercise from <Link href="/history" className="text-accent">History</Link> and choose Review.
          </div>
        )}
        {error && <div className="bg-surface-2 border-l-4 border-signal-red rounded p-3 text-signal-red text-sm">{error}</div>}

        {enabled && exerciseId && (
          <div className="grid lg:grid-cols-[320px_1fr] gap-4">
            <div className="bg-surface-1 border border-border-1 rounded divide-y divide-border-1 max-h-[80vh] overflow-y-auto">
              {rows.map(r => (
                <button key={r.index} onClick={() => setSel(r.index)}
                  className={`w-full text-left p-3 text-sm hover:bg-surface-2 ${sel === r.index ? 'bg-surface-2' : ''}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">Case {r.case_num}</span>
                    <Chip status={r.status} />
                  </div>
                  <div className="text-ink-2 truncate">{r.title}</div>
                  <div className="text-xs text-ink-3 font-mono">
                    D{r.day ?? '?'} {r.arrival ?? ''} · {r.pathway ?? '—'} · RT {r.red_team?.high ?? 0}H/{r.red_team?.medium ?? 0}M
                    {r.open_comments ? ` · ${r.open_comments} open` : ''}
                  </div>
                </button>
              ))}
            </div>

            {detail && ctrl ? (
              <div className="space-y-4">
                <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm space-y-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-lg font-display">Case {detail.index + 1}: {detail.case.meta?.title}</h2>
                    <Chip status={detail.review.status} />
                  </div>
                  <p className="text-ink-2">{PATHWAY_LABELS[ctrl.pathway] || ctrl.pathway} · {ctrl.chain.nodes.map(n => n.name).join(' → ')}</p>
                  {detail.review.reviewer && <p className="text-ink-3 text-xs">Last decision by {detail.review.reviewer}{detail.review.decided_at ? ` on ${detail.review.decided_at.slice(0, 10)}` : ''}{detail.review.note ? ` — ${detail.review.note}` : ''}</p>}
                  {ctrl.moulage && <p><span className="text-ink-3">Moulage:</span> {ctrl.moulage}</p>}
                </div>

                <div className="bg-surface-1 border border-border-1 rounded p-4">
                  <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-2">Red-team findings (click to comment on one)</p>
                  <ul className="space-y-1 text-sm">
                    {(ctrl.red_team?.open || []).length === 0 && <li className="text-ink-3">None open.</li>}
                    {(ctrl.red_team?.open || []).map((f: Finding, i: number) => (
                      <li key={i}>
                        <button className="text-left hover:underline" onClick={() => { setTarget(f.location || 'general'); setSeverity(f.severity); setBody(`Re: ${f.issue} — `); }}>
                          <span className={f.severity === 'high' ? 'text-signal-red' : f.severity === 'medium' ? 'text-signal-amber' : 'text-ink-3'}>[{f.severity}/{f.source}]</span>{' '}
                          {f.issue} <span className="text-ink-3">Fix: {f.fix}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="bg-surface-1 border border-border-1 rounded p-4">
                  <div className="flex flex-wrap gap-2 mb-3">
                    {ctrl.legs.map(l => (
                      <button key={l.leg_id} onClick={() => setLegId(l.leg_id)}
                        className={`px-3 py-1 rounded text-xs border ${leg?.leg_id === l.leg_id ? 'bg-accent text-accent-on border-accent' : 'bg-surface-2 border-border-1 text-ink-2'}`}>
                        {l.title}{l.focus ? ' ★' : ''}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-ink-3 mb-2">Click a box to pin your comment to it.</p>
                  {leg && <TreeView leg={leg} reached={new Set(target.startsWith(`legs[${leg.leg_id}]`) ? [target.split('.').pop() || ''] : [])}
                    onToggle={id => setTarget(`legs[${leg.leg_id}].tree.${id}`)} />}
                  <div className="overflow-x-auto mt-4">
                    {(['green', 'red'] as const).map(k => (
                      <table key={k} className="text-xs font-mono mb-3 border-collapse">
                        <tbody>
                          <tr>
                            <th className={`px-2 text-left ${k === 'red' ? 'text-signal-red' : 'text-signal-green'}`}>{k}</th>
                            {ctrl.vitals_tracks[k].map(p => (
                              <th key={p.t} className="px-2 cursor-pointer hover:underline" onClick={() => setTarget(`vitals_tracks.${k}@${p.t}`)}>{p.t}</th>
                            ))}
                          </tr>
                          {([['BP', (p: Vitals) => `${p.sbp}/${p.dbp}`], ['HR', p => p.hr], ['RR', p => p.rr], ['SpO2', p => p.spo2],
                            ['AVPU', p => p.avpu], ['GCS', p => `${p.gcs_e}/${p.gcs_v}/${p.gcs_m}`]] as [string, (p: Vitals) => unknown][]).map(([lbl, fn]) => (
                            <tr key={lbl}>
                              <td className="px-2 text-ink-3">{lbl}</td>
                              {ctrl.vitals_tracks[k].map(p => <td key={p.t} className="px-2 text-center">{String(fn(p) ?? '')}</td>)}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ))}
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-caps text-ink-3">Comments</p>
                    {detail.comments.length === 0 && <p className="text-ink-3">No comments yet.</p>}
                    {detail.comments.map(c => (
                      <div key={c.id} className={`border-l-2 pl-2 ${c.resolved ? 'border-border-1 opacity-60' : c.severity === 'high' ? 'border-signal-red' : 'border-signal-amber'}`}>
                        <div className="text-xs text-ink-3">{c.author} · {c.target} · {c.severity}{c.created_at ? ` · ${c.created_at.slice(0, 16).replace('T', ' ')}` : ''}</div>
                        <div>{c.body}</div>
                        <button disabled={busy} onClick={() => call(`/exercises/${exerciseId}/review/${detail.index}/comments/${c.id}`, 'PATCH', { resolved: !c.resolved })}
                          className="text-xs text-accent hover:text-accent-hover">{c.resolved ? 'Reopen' : 'Resolve'}</button>
                      </div>
                    ))}
                    <div className="pt-2 space-y-2 border-t border-border-1">
                      <div className="flex gap-2">
                        <input value={target} onChange={e => setTarget(e.target.value)} className="flex-1 bg-surface-2 border border-border-1 rounded px-2 py-1 text-xs font-mono" aria-label="Comment target" />
                        <select value={severity} onChange={e => setSeverity(e.target.value)} className="bg-surface-2 border border-border-1 rounded px-2 text-xs" aria-label="Severity">
                          <option value="high">high</option><option value="medium">medium</option><option value="low">low</option>
                        </select>
                      </div>
                      <textarea value={body} onChange={e => setBody(e.target.value)} rows={3} placeholder="What's wrong and what it should be"
                        className="w-full bg-surface-2 border border-border-1 rounded px-2 py-1" />
                      <button disabled={busy} onClick={addComment} className="px-3 py-1.5 rounded bg-accent hover:bg-accent-hover text-accent-on text-xs font-semibold uppercase tracking-caps">Add comment</button>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm space-y-2">
                      <p className="text-xs font-semibold uppercase tracking-caps text-ink-3">Decision</p>
                      <select value={decision} onChange={e => setDecision(e.target.value)} className="w-full bg-surface-2 border border-border-1 rounded px-2 py-1" aria-label="Decision">
                        <option value="approved">Approve for use</option>
                        <option value="changes_requested">Changes required</option>
                        <option value="in_review">Back to in review</option>
                      </select>
                      <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder="Note (optional)" className="w-full bg-surface-2 border border-border-1 rounded px-2 py-1" />
                      {(ctrl.red_team?.counts?.high ?? 0) > 0 && decision === 'approved' && (
                        <label className="flex items-start gap-2 text-xs text-signal-amber">
                          <input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} className="mt-0.5" />
                          I have reviewed the {ctrl.red_team?.counts?.high} open high-severity red-team finding(s) and they are acceptable as written.
                        </label>
                      )}
                      <button disabled={busy} onClick={decide} className="px-3 py-1.5 rounded bg-accent hover:bg-accent-hover text-accent-on text-xs font-semibold uppercase tracking-caps">Record decision</button>
                    </div>

                    <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold uppercase tracking-caps text-ink-3">Edit controller layer</p>
                        <button onClick={() => setEditing(v => !v)} className="text-xs text-accent hover:text-accent-hover">{editing ? 'Cancel' : 'Edit JSON'}</button>
                      </div>
                      {editing ? (
                        <>
                          <textarea value={editText} onChange={e => setEditText(e.target.value)} rows={18} spellCheck={false}
                            className="w-full bg-surface-2 border border-border-1 rounded px-2 py-1 font-mono text-xs" />
                          <input value={editSummary} onChange={e => setEditSummary(e.target.value)} placeholder="What you changed"
                            className="w-full bg-surface-2 border border-border-1 rounded px-2 py-1" />
                          <button disabled={busy} onClick={saveEdit} className="px-3 py-1.5 rounded bg-accent hover:bg-accent-hover text-accent-on text-xs font-semibold uppercase tracking-caps">Save and re-check</button>
                          <p className="text-xs text-ink-3">Saving re-runs the rules red team and returns the case to In review.</p>
                        </>
                      ) : (
                        <p className="text-xs text-ink-3">Fix vitals, tree boxes, laterality or doses directly. The care chain can&apos;t be edited here, because it comes from the WARNO and FRAGOs.</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-surface-1 border border-border-1 rounded p-6 text-sm text-ink-3">
                {detail && !ctrl ? 'This case predates decision trees and has nothing to review.' : 'Select a case.'}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
