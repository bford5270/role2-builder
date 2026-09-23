'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { PATHWAY_LABELS } from '@/lib/controller';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://role2-builder-production.up.railway.app';

interface LibCase {
  exercise_id: number; exercise: string; index: number; title?: string; mechanism?: string;
  pathway?: string; triage?: string; reviewer?: string; decided_at?: string;
}

export default function LibraryPage() {
  const [cases, setCases] = useState<LibCase[] | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [q, setQ] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/library`)
      .then(r => r.json())
      .then(d => { setEnabled(d.enabled); setCases(d.cases); })
      .catch(() => setError('Could not load the library'));
  }, []);

  const shown = (cases || []).filter(c =>
    !q || `${c.title} ${c.mechanism} ${c.pathway} ${c.exercise}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="min-h-screen bg-surface-0 text-ink-1 p-4 md:p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold font-display tracking-display">Scenario library</h1>
            <p className="text-ink-3 text-sm">Cases approved by expert reviewers</p>
          </div>
          <div className="flex gap-3 text-sm">
            <Link href="/history" className="text-accent hover:text-accent-hover">History</Link>
            <Link href="/controller" className="text-accent hover:text-accent-hover">Live controller</Link>
          </div>
        </div>
        {error && <div className="bg-surface-2 border-l-4 border-signal-red rounded p-3 text-signal-red text-sm">{error}</div>}
        {!enabled && <div className="bg-surface-1 border border-border-1 rounded p-4 text-sm text-ink-2">Review storage isn&apos;t configured on this server yet.</div>}
        {enabled && cases && (
          <>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter by injury, mechanism, pathway…"
              className="w-full bg-surface-1 border border-border-1 rounded px-3 py-2 text-sm" />
            {shown.length === 0 && <p className="text-ink-3 text-sm">No approved cases yet.</p>}
            <div className="space-y-2">
              {shown.map(c => (
                <div key={`${c.exercise_id}-${c.index}`} className="bg-surface-1 border border-border-1 rounded p-3 flex flex-wrap items-center justify-between gap-3 text-sm">
                  <div>
                    <div className="font-medium">{c.title}</div>
                    <div className="text-xs text-ink-3">{c.mechanism} · {PATHWAY_LABELS[c.pathway || ''] || c.pathway} · {c.triage} · from {c.exercise} (case {c.index + 1})</div>
                    <div className="text-xs text-signal-green">Approved by {c.reviewer}{c.decided_at ? ` on ${c.decided_at.slice(0, 10)}` : ''}</div>
                  </div>
                  <div className="flex gap-2">
                    <Link href={`/review?exercise=${c.exercise_id}`} className="px-3 py-1 bg-surface-2 hover:bg-surface-3 border border-border-1 rounded text-xs">Review</Link>
                    <a href={`${API_BASE}/library/${c.exercise_id}/${c.index}`} className="px-3 py-1 bg-accent hover:bg-accent-hover text-accent-on rounded text-xs">Download JSON</a>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
