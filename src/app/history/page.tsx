'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { API_BASE } from '@/lib/api';

interface ExerciseSummary {
  id: number;
  name: string;
  created_at: string | null;
  duration: number | null;
  environment: string | null;
  total_cases: number;
  region?: string | null;
  threat_level?: string | null;
  supported_unit?: string | null;
  days?: number | null;
}

interface CaseRow {
  index: number;
  zap: string | null;
  title: string | null;
  triage: string | null;
  disposition: string | null;
  specialty: string | null;
  duration: string | null;
  mechanism: string;
  injuries: string;
}

interface CaseDetail {
  index: number;
  has_controller: boolean;
  schedule: Record<string, unknown> | null;
  case: Record<string, unknown>;
}

interface Group {
  key: string;
  name: string;
  runs: ExerciseSummary[]; // newest first
}

type SortKey = 'newest' | 'oldest' | 'cases' | 'name';

// Case data never changes once archived, so each list/detail is fetched at most once per page load.
const caseListCache = new Map<number, CaseRow[]>();
const caseDetailCache = new Map<string, CaseDetail>();

const DOCUMENTS: { key: string; label: string; ext: string; file: string }[] = [
  { key: 'msel', label: 'MSEL', ext: 'xlsx', file: 'MSEL' },
  { key: 'warno', label: 'WARNO', ext: 'docx', file: 'WARNO' },
  { key: 'annex_q', label: 'Annex Q', ext: 'docx', file: 'Annex_Q' },
  { key: 'medroe', label: 'MEDROE', ext: 'docx', file: 'MEDROE' },
  { key: 'case_book', label: 'Case book', ext: 'docx', file: 'Case_Book' },
  { key: 'road_to_war', label: 'Road to War', ext: 'docx', file: 'Road_to_War_Prompt' },
  { key: 'fragos', label: 'FRAGOs', ext: 'docx', file: 'FRAGOs' },
  { key: 'controller_packet', label: 'Controller packet', ext: 'docx', file: 'Controller_Packet' },
  { key: 'controller_vitals', label: 'Controller vitals', ext: 'xlsx', file: 'Controller_Vitals' },
  { key: 'cases_json', label: 'cases.json', ext: 'json', file: 'cases' },
];

const NINE_LINE_LABELS: Record<string, string> = {
  line1_location: '1 · Location',
  line2_freq: '2 · Frequency / call sign',
  line3_patients_precedence: '3 · Patients by precedence',
  line4_equipment: '4 · Special equipment',
  line5_patients_type: '5 · Patients by type',
  line6_security: '6 · Security',
  line7_marking: '7 · Marking',
  line8_nationality: '8 · Nationality / status',
  line9_nbc_terrain: '9 · NBC / terrain',
};

const str = (v: unknown): string => (typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '');
const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

const triageKey = (t: string | null): string => {
  const m = (t || '').match(/T\s*([1-4])/i);
  return m ? `T${m[1]}` : 'Other';
};

const TRIAGE_STYLE: Record<string, string> = {
  T1: 'border-signal-red text-signal-red',
  T2: 'border-signal-amber text-signal-amber',
  T3: 'border-signal-green text-signal-green',
  T4: 'border-signal-blue text-signal-blue',
  Other: 'border-border-2 text-ink-3',
};

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return 'N/A';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
};

const nameKey = (name: string) => name.trim().toLowerCase() || '(unnamed)';

function TriageBadge({ triage }: { triage: string | null }) {
  const key = triageKey(triage);
  return (
    <span className={`inline-block border rounded px-1.5 py-0.5 text-xs font-mono ${TRIAGE_STYLE[key]}`}>
      {key === 'Other' ? (triage || '—') : key}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="mb-2">
      <p className="text-xs uppercase tracking-caps text-ink-3">{label}</p>
      <p className="text-sm text-ink-1 whitespace-pre-line">{value}</p>
    </div>
  );
}

function BulletList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mb-2">
      <p className="text-xs uppercase tracking-caps text-ink-3">{label}</p>
      <ul className="list-disc ml-5 text-sm text-ink-1 space-y-0.5">
        {items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    </div>
  );
}

function CaseDetailView({ detail }: { detail: CaseDetail }) {
  const c = detail.case;
  const meta = obj(c.meta);
  const zmist = obj(c.zmist);
  const nineLine = obj(c.nine_line);
  const evac = obj(c.evacuation);
  const phases = obj(c.phases);
  const sched = detail.schedule;
  return (
    <div className="bg-surface-0 border border-border-1 rounded p-4 mt-2 space-y-4">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-ink-2">
        {str(meta.target_specialty) && <span>Specialty: <span className="text-ink-1">{str(meta.target_specialty)}</span></span>}
        {str(meta.estimated_duration) && <span>Duration: <span className="text-ink-1">{str(meta.estimated_duration)}</span></span>}
        {sched && str(sched.day) && <span>Day: <span className="text-ink-1">{str(sched.day)}</span></span>}
        {sched && str(sched.time) && <span>Time: <span className="text-ink-1 font-mono">{str(sched.time)}</span></span>}
        {sched && str(sched.care_level) && <span>Care level: <span className="text-ink-1">{str(sched.care_level)}</span></span>}
        {str(c.disposition) && <span>Disposition: <span className="text-ink-1">{str(c.disposition)}</span></span>}
      </div>
      {str(meta.personnel) && <Field label="Personnel" value={str(meta.personnel)} />}

      <div>
        <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-2">ZMIST</p>
        <Field label="Mechanism" value={str(zmist.mechanism)} />
        <Field label="Injuries" value={str(zmist.injuries)} />
        <Field label="Signs" value={str(zmist.signs)} />
        <Field label="Treatment" value={str(zmist.treatment)} />
      </div>

      {Object.keys(nineLine).length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-2">9-Line MEDEVAC</p>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
            {Object.entries(nineLine).map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-ink-3">{NINE_LINE_LABELS[k] || k}</dt>
                <dd className="text-ink-1">{str(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {(['dcr', 'dcs', 'pcc'] as const).map((phase) => {
        const p = obj(phases[phase]);
        if (!str(p.title) && !str(p.narrative)) return null;
        const contingencies = arr(p.contingencies).map((x) => {
          const o = obj(x);
          return [str(o.condition), str(o.intervention)].filter(Boolean).join(' → ');
        }).filter(Boolean);
        return (
          <div key={phase}>
            <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-2">
              {phase.toUpperCase()}{str(p.title) ? ` — ${str(p.title)}` : ''}
            </p>
            <Field label="Narrative" value={str(p.narrative)} />
            <BulletList label="Expected actions" items={arr(p.expected_actions).map(str).filter(Boolean)} />
            <BulletList label="Contingencies" items={contingencies} />
          </div>
        );
      })}

      {Object.keys(evac).length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-2">Evacuation</p>
          <Field label="Transport" value={str(evac.transport_type)} />
          <Field label="Priority" value={str(evac.priority)} />
          <Field label="Considerations" value={str(evac.considerations)} />
          <Field label="Handover" value={str(evac.handover_notes)} />
        </div>
      )}

      <BulletList label="Learning objectives" items={arr(c.learning_objectives).map(str).filter(Boolean)} />
      <BulletList label="Debrief questions" items={arr(c.debrief_questions).map(str).filter(Boolean)} />
      <p className="text-xs text-ink-3">
        Vitals trends, labs and the controller decision trees are in the Case book, Controller packet and cases.json downloads.
      </p>
    </div>
  );
}

function CasePanel({ exerciseId }: { exerciseId: number }) {
  const [rows, setRows] = useState<CaseRow[] | null>(caseListCache.get(exerciseId) ?? null);
  const [error, setError] = useState<string | null>(null);
  const [triageFilter, setTriageFilter] = useState<string>('all');
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    if (caseListCache.has(exerciseId)) return;
    let cancelled = false;
    fetch(`${API_BASE}/exercises/${exerciseId}/cases`)
      .then((r) => { if (!r.ok) throw new Error('Failed to load cases'); return r.json(); })
      .then((d) => { caseListCache.set(exerciseId, d.cases); if (!cancelled) setRows(d.cases); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load cases'); });
    return () => { cancelled = true; };
  }, [exerciseId]);

  const openCase = async (index: number) => {
    if (openIndex === index) { setOpenIndex(null); setDetail(null); return; }
    setOpenIndex(index);
    setError(null);
    const cacheKey = `${exerciseId}:${index}`;
    const cached = caseDetailCache.get(cacheKey);
    if (cached) { setDetail(cached); return; }
    setDetail(null);
    setDetailLoading(true);
    try {
      const r = await fetch(`${API_BASE}/exercises/${exerciseId}/cases/${index}`);
      if (!r.ok) throw new Error('Failed to load case');
      const d: CaseDetail = await r.json();
      caseDetailCache.set(cacheKey, d);
      setDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load case');
    } finally {
      setDetailLoading(false);
    }
  };

  const mix = useMemo(() => {
    const counts: Record<string, number> = {};
    (rows || []).forEach((r) => { const k = triageKey(r.triage); counts[k] = (counts[k] || 0) + 1; });
    return counts;
  }, [rows]);

  if (error && !rows) return <p className="text-signal-red text-sm mt-3">{error}</p>;
  if (!rows) return <p className="text-ink-3 text-sm mt-3">Loading cases…</p>;

  const visible = triageFilter === 'all' ? rows : rows.filter((r) => triageKey(r.triage) === triageFilter);

  return (
    <div className="border-t border-border-1 mt-3 pt-3">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <button
          onClick={() => setTriageFilter('all')}
          className={`px-2 py-1 rounded text-xs border ${triageFilter === 'all' ? 'bg-accent text-accent-on border-accent' : 'bg-surface-2 text-ink-2 border-border-1'}`}
        >
          All {rows.length}
        </button>
        {Object.entries(mix).sort().map(([k, n]) => (
          <button
            key={k}
            onClick={() => setTriageFilter(triageFilter === k ? 'all' : k)}
            className={`px-2 py-1 rounded text-xs border bg-surface-2 ${TRIAGE_STYLE[k]} ${triageFilter === k ? 'ring-1 ring-current' : ''}`}
          >
            {k} {n}
          </button>
        ))}
      </div>
      {error && <p className="text-signal-red text-sm mb-2">{error}</p>}
      <ul className="divide-y divide-border-1 border border-border-1 rounded">
        {visible.map((r) => (
          <li key={r.index}>
            <button
              onClick={() => openCase(r.index)}
              className="w-full text-left px-3 py-2 hover:bg-surface-2 flex items-start gap-3"
              aria-expanded={openIndex === r.index}
            >
              <span className="w-8 shrink-0 font-mono text-xs text-ink-3 pt-0.5">#{r.index + 1}</span>
              <span className="shrink-0 pt-0.5"><TriageBadge triage={r.triage} /></span>
              <span className="min-w-0">
                <span className="block text-sm text-ink-1">{r.title || 'Untitled case'}</span>
                <span className="block text-xs text-ink-3 truncate">
                  {[r.zap && `ZAP ${r.zap}`, r.disposition, r.specialty].filter(Boolean).join(' · ')}
                </span>
                {openIndex !== r.index && r.mechanism && (
                  <span className="block text-xs text-ink-2 mt-0.5">{r.mechanism}</span>
                )}
              </span>
            </button>
            {openIndex === r.index && (
              <div className="px-3 pb-3">
                {detailLoading && <p className="text-ink-3 text-sm py-2">Loading case…</p>}
                {detail && detail.index === r.index && <CaseDetailView detail={detail} />}
              </div>
            )}
          </li>
        ))}
        {visible.length === 0 && <li className="px-3 py-4 text-sm text-ink-3">No cases match this filter.</li>}
      </ul>
    </div>
  );
}

export default function HistoricExercisesPage() {
  const [exercises, setExercises] = useState<ExerciseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<number | null>(null);

  const [query, setQuery] = useState('');
  const [environment, setEnvironment] = useState('all');
  const [sort, setSort] = useState<SortKey>('newest');
  const [grouped, setGrouped] = useState(true);
  const [showEarlier, setShowEarlier] = useState<Set<string>>(new Set());
  const [openCases, setOpenCases] = useState<Set<number>>(new Set());

  // Loaded once; filtering, grouping and sorting then happen in the browser with no further requests.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${API_BASE}/exercises`);
        if (!response.ok) throw new Error('Failed to fetch exercises');
        const data = await response.json();
        if (!cancelled) setExercises(data.exercises);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load exercises');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const saveBlob = async (url: string, filename: string, failure: string) => {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(failure);
      const blob = await response.blob();
      const href = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(href);
      document.body.removeChild(a);
    } catch {
      alert(failure);
    }
  };

  const downloadPackage = async (exerciseId: number, exerciseName: string) => {
    setDownloading(exerciseId);
    await saveBlob(`${API_BASE}/exercises/${exerciseId}/download`, `${exerciseName}_Package.zip`, 'Failed to download package');
    setDownloading(null);
  };

  const downloadDocument = (exerciseId: number, exerciseName: string, doc: (typeof DOCUMENTS)[number]) =>
    saveBlob(`${API_BASE}/exercises/${exerciseId}/document/${doc.key}`, `${exerciseName}_${doc.file}.${doc.ext}`, 'Failed to download document');

  const environments = useMemo(
    () => Array.from(new Set(exercises.map((e) => e.environment).filter((v): v is string => !!v))).sort(),
    [exercises],
  );

  // All filtering, grouping and sorting happens in the browser on the already-loaded list.
  const groups: Group[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = exercises.filter((e) => {
      if (environment !== 'all' && e.environment !== environment) return false;
      if (!q) return true;
      return [e.name, e.environment, e.region, e.supported_unit, e.threat_level]
        .some((f) => (f || '').toLowerCase().includes(q));
    });
    const byDate = (a: ExerciseSummary, b: ExerciseSummary) => (b.created_at || '').localeCompare(a.created_at || '');
    const buckets = new Map<string, ExerciseSummary[]>();
    matches.forEach((e) => {
      const key = grouped ? nameKey(e.name || '') : `#${e.id}`;
      buckets.set(key, [...(buckets.get(key) || []), e]);
    });
    const out: Group[] = Array.from(buckets.entries()).map(([key, runs]) => {
      const sorted = [...runs].sort(byDate);
      return { key, name: sorted[0].name || '(Unnamed exercise)', runs: sorted };
    });
    const newest = (g: Group) => g.runs[0].created_at || '';
    const oldest = (g: Group) => g.runs[g.runs.length - 1].created_at || '';
    const maxCases = (g: Group) => Math.max(...g.runs.map((r) => r.total_cases));
    out.sort((a, b) => {
      if (sort === 'oldest') return oldest(a).localeCompare(oldest(b));
      if (sort === 'cases') return maxCases(b) - maxCases(a);
      if (sort === 'name') return a.name.localeCompare(b.name);
      return newest(b).localeCompare(newest(a));
    });
    return out;
  }, [exercises, query, environment, sort, grouped]);

  const shownRuns = groups.reduce((n, g) => n + g.runs.length, 0);

  const toggle = <T,>(set: Set<T>, value: T, update: (s: Set<T>) => void) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value); else next.add(value);
    update(next);
  };

  const renderRun = (exercise: ExerciseSummary, label?: string) => (
    <div key={exercise.id} className="bg-surface-1 border border-border-1 rounded p-4">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h2 className="text-lg font-medium font-display text-ink-1">{label ?? (exercise.name || '(Unnamed exercise)')}</h2>
          <p className="text-xs font-mono text-ink-3 mt-0.5">{formatDate(exercise.created_at)} · run #{exercise.id}</p>
        </div>
        <button
          onClick={() => downloadPackage(exercise.id, exercise.name)}
          disabled={downloading === exercise.id}
          className={`px-4 py-2 rounded font-semibold text-xs uppercase tracking-caps transition-colors shrink-0 ${
            downloading === exercise.id ? 'bg-surface-3 text-ink-3 cursor-wait' : 'bg-accent hover:bg-accent-hover text-accent-on'
          }`}
        >
          {downloading === exercise.id ? 'Downloading...' : 'Download zip'}
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 mb-3 text-sm">
        {([
          ['Duration', `${exercise.duration || 'N/A'} days`],
          ['Environment', exercise.environment || 'N/A'],
          ['Cases', String(exercise.total_cases)],
          ['Region', exercise.region || ''],
          ['Threat', exercise.threat_level || ''],
          ['Unit', exercise.supported_unit || ''],
        ] as [string, string][]).filter(([, v]) => v).map(([k, v]) => (
          <div key={k}>
            <span className="text-xs uppercase tracking-caps text-ink-3">{k}</span>
            <span className="ml-2 text-ink-1">{v}</span>
          </div>
        ))}
      </div>

      <div className="border-t border-border-1 pt-3">
        <div className="flex flex-wrap gap-2 mb-3">
          <a href={`/controller?exercise=${exercise.id}`} className="px-3 py-1 bg-accent hover:bg-accent-hover text-accent-on rounded text-xs font-semibold">Live controller</a>
          <button
            onClick={() => toggle(openCases, exercise.id, setOpenCases)}
            aria-expanded={openCases.has(exercise.id)}
            className="px-3 py-1 bg-surface-2 hover:bg-surface-3 border border-border-1 text-ink-1 rounded text-xs font-semibold"
          >
            {openCases.has(exercise.id) ? 'Hide cases' : `View cases (${exercise.total_cases})`}
          </button>
        </div>
        <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-2">Individual documents</p>
        <div className="flex flex-wrap gap-2">
          {DOCUMENTS.map((doc) => (
            <button
              key={doc.key}
              onClick={() => downloadDocument(exercise.id, exercise.name, doc)}
              className="px-3 py-1 bg-surface-2 hover:bg-surface-3 border border-border-1 text-ink-2 rounded text-xs transition-colors"
            >
              {doc.label}
            </button>
          ))}
        </div>
        {openCases.has(exercise.id) && <CasePanel exerciseId={exercise.id} />}
      </div>
    </div>
  );

  const inputClass = 'bg-surface-1 border border-border-1 rounded px-3 py-2 text-sm text-ink-1';

  return (
    <div className="min-h-screen bg-surface-0 text-ink-1 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold font-display tracking-display text-ink-1">Historic exercises</h1>
            <p className="text-ink-3 text-sm">Browse, review and download past exercise packages</p>
          </div>
          <Link href="/" className="text-accent hover:text-accent-hover text-sm">← New exercise</Link>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-12 text-ink-2">
            <svg className="animate-spin h-6 w-6 text-accent" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="ml-3">Loading exercises...</span>
          </div>
        )}

        {error && (
          <div className="bg-surface-2 border-l-4 border-signal-red rounded p-4 mb-6">
            <p className="text-signal-red text-sm">{error}</p>
          </div>
        )}

        {!loading && exercises.length === 0 && !error && (
          <div className="bg-surface-1 border border-border-1 rounded p-8 text-center">
            <p className="text-ink-3 mb-4">No exercises found.</p>
            <Link href="/" className="text-accent hover:text-accent-hover underline">Create your first exercise →</Link>
          </div>
        )}

        {exercises.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name, region, unit…"
              aria-label="Search exercises"
              className={`${inputClass} flex-1 min-w-[12rem]`}
            />
            <select value={environment} onChange={(e) => setEnvironment(e.target.value)} aria-label="Environment" className={inputClass}>
              <option value="all">All environments</option>
              {environments.map((env) => <option key={env} value={env}>{env}</option>)}
            </select>
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Sort" className={inputClass}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="cases">Most cases</option>
              <option value="name">Name A–Z</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} />
              Group repeat runs
            </label>
          </div>
        )}

        {exercises.length > 0 && (
          <p className="text-xs text-ink-3 mb-3">
            Showing {shownRuns} of {exercises.length} runs{grouped ? ` in ${groups.length} ${groups.length === 1 ? 'exercise' : 'exercises'}` : ''}
          </p>
        )}

        {exercises.length > 0 && groups.length === 0 && (
          <div className="bg-surface-1 border border-border-1 rounded p-6 text-center text-ink-3 text-sm">
            No exercises match these filters.
          </div>
        )}

        <div className="space-y-4">
          {groups.map((g) => {
            const [latest, ...earlier] = g.runs;
            const open = showEarlier.has(g.key);
            return (
              <div key={g.key}>
                {renderRun(latest)}
                {earlier.length > 0 && (
                  <div className="ml-4 sm:ml-8 mt-2 border-l-2 border-border-1 pl-4">
                    <button
                      onClick={() => toggle(showEarlier, g.key, setShowEarlier)}
                      aria-expanded={open}
                      className="text-xs text-accent hover:text-accent-hover mb-2"
                    >
                      {open ? 'Hide' : 'Show'} {earlier.length} earlier {earlier.length === 1 ? 'run' : 'runs'} of “{g.name}”
                    </button>
                    {open && <div className="space-y-3">{earlier.map((r) => renderRun(r))}</div>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
