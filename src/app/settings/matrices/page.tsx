'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://role2-builder-production.up.railway.app';

type Triage = 'T1' | 'T2' | 'T3' | 'T4';
const TRIAGE: Triage[] = ['T1', 'T2', 'T3', 'T4'];

interface MatrixView {
  trauma_ratio_by_setting: Record<string, number>;
  threat_level_shift: Record<string, Record<string, number>>;
  base_triage_distribution: Record<string, Record<string, number>>;
  mascal_triage_distribution: Record<string, number>;
  etiology_by_setting: Record<string, string[]>;
  dnbi_by_region: Record<string, string[]>;
  cbrn_etiologies: Record<string, string[]>;
}

interface SettingsBody {
  overrides: Record<string, unknown>;
  view: MatrixView;
  defaults: MatrixView;
}

interface PresetSummary {
  name: string;
  label: string;
  description: string;
}

const round3 = (n: number) => Math.round(n * 1000) / 1000;

// Diff helpers — only send changed fields back as overrides.
function diffNumericByKey(
  current: Record<string, number>,
  defaults: Record<string, number>,
): Record<string, number> | null {
  const out: Record<string, number> = {};
  let changed = false;
  for (const k of Object.keys(current)) {
    if (Math.abs((current[k] ?? 0) - (defaults[k] ?? 0)) > 1e-6) {
      out[k] = current[k];
      changed = true;
    }
  }
  return changed ? out : null;
}

function diffNestedNumeric(
  current: Record<string, Record<string, number>>,
  defaults: Record<string, Record<string, number>>,
): Record<string, Record<string, number>> | null {
  const out: Record<string, Record<string, number>> = {};
  let changed = false;
  for (const outer of Object.keys(current)) {
    const inner = current[outer];
    const def = defaults[outer] || {};
    let innerChanged = false;
    for (const k of Object.keys(inner)) {
      if (Math.abs((inner[k] ?? 0) - (def[k] ?? 0)) > 1e-6) {
        innerChanged = true;
      }
    }
    if (innerChanged) {
      out[outer] = inner;
      changed = true;
    }
  }
  return changed ? out : null;
}

function diffStringList(
  current: Record<string, string[]>,
  defaults: Record<string, string[]>,
): Record<string, string[]> | null {
  const out: Record<string, string[]> = {};
  let changed = false;
  for (const k of Object.keys(current)) {
    const a = current[k];
    const b = defaults[k] || [];
    if (a.length !== b.length || a.some((v, i) => v !== b[i])) {
      out[k] = a;
      changed = true;
    }
  }
  return changed ? out : null;
}

export default function MatricesSettingsPage() {
  const [data, setData] = useState<SettingsBody | null>(null);
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  // Editable copy of `view`. We diff against `defaults` at save time.
  const [draft, setDraft] = useState<MatrixView | null>(null);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, p] = await Promise.all([
        fetch(`${API_BASE}/settings/matrices`).then((r) => r.json()),
        fetch(`${API_BASE}/settings/matrices/presets`).then((r) => r.json()),
      ]);
      setData(s);
      setDraft(JSON.parse(JSON.stringify(s.view)));
      setPresets(p.presets);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const onSave = async () => {
    if (!draft || !data) return;
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const overrides: Record<string, unknown> = {};
      const traumaDiff = diffNumericByKey(draft.trauma_ratio_by_setting, data.defaults.trauma_ratio_by_setting);
      if (traumaDiff) overrides.trauma_ratio_by_setting = traumaDiff;
      const triageDiff = diffNestedNumeric(draft.base_triage_distribution, data.defaults.base_triage_distribution);
      if (triageDiff) overrides.base_triage_distribution = triageDiff;
      const threatDiff = diffNestedNumeric(draft.threat_level_shift, data.defaults.threat_level_shift);
      if (threatDiff) overrides.threat_level_shift = threatDiff;
      const mascalDiff = diffNumericByKey(draft.mascal_triage_distribution, data.defaults.mascal_triage_distribution);
      if (mascalDiff) overrides.mascal_triage_distribution = mascalDiff;
      const etiologyDiff = diffStringList(draft.etiology_by_setting, data.defaults.etiology_by_setting);
      if (etiologyDiff) overrides.etiology_by_setting = etiologyDiff;
      const dnbiDiff = diffStringList(draft.dnbi_by_region, data.defaults.dnbi_by_region);
      if (dnbiDiff) overrides.dnbi_by_region = dnbiDiff;
      const cbrnDiff = diffStringList(draft.cbrn_etiologies, data.defaults.cbrn_etiologies);
      if (cbrnDiff) overrides.cbrn_etiologies = cbrnDiff;

      const r = await fetch(`${API_BASE}/settings/matrices`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(overrides),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail ? JSON.stringify(body.detail) : 'Save failed');
      }
      setStatus(Object.keys(overrides).length === 0 ? 'No changes to save.' : 'Saved.');
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const onReset = async () => {
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const r = await fetch(`${API_BASE}/settings/matrices`, { method: 'DELETE' });
      if (!r.ok) throw new Error('Reset failed');
      setStatus('Reset to defaults.');
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setSaving(false);
    }
  };

  const onApplyPreset = async (name: string) => {
    if (!name) return;
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const r = await fetch(`${API_BASE}/settings/matrices/presets/${name}/apply`, { method: 'POST' });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || 'Preset apply failed');
      }
      setStatus(`Applied preset: ${name}`);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Preset apply failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading || !draft || !data) {
    return (
      <div className="min-h-screen bg-stone-900 text-amber-100 p-8 flex items-center justify-center">
        <p>{error ? error : 'Loading…'}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-stone-900 text-amber-100 p-6">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-amber-400">Matrix Configuration</h1>
          <a href="/" className="text-amber-400 hover:text-amber-300 text-sm">← Back to Setup</a>
        </div>

        <p className="text-stone-400 mb-6 text-sm">
          These values shape how exercise inputs translate into casualty types and triage distributions.
          Changes here apply to <em>all subsequent</em> exercises until you reset. Each generated exercise
          carries a snapshot of the matrix that produced it.
        </p>

        {error && <div className="bg-red-900/50 border border-red-700 rounded-lg p-3 mb-4 text-red-300 text-sm">{error}</div>}
        {status && <div className="bg-emerald-900/50 border border-emerald-700 rounded-lg p-3 mb-4 text-emerald-300 text-sm">{status}</div>}

        {/* Presets */}
        <section className="bg-stone-800 border border-stone-700 rounded-lg p-4 mb-6">
          <h2 className="text-amber-400 font-semibold mb-3">Presets</h2>
          <div className="flex items-center gap-3 flex-wrap">
            <select
              defaultValue=""
              onChange={(e) => {
                const v = e.target.value;
                if (v) onApplyPreset(v);
                e.target.value = '';
              }}
              disabled={saving}
              className="bg-stone-700 border border-stone-600 rounded px-3 py-2 text-sm"
            >
              <option value="" disabled>Apply preset…</option>
              {presets.map((p) => (
                <option key={p.name} value={p.name}>{p.label}</option>
              ))}
            </select>
            <button
              onClick={onReset}
              disabled={saving}
              className="text-sm px-3 py-2 rounded border border-stone-500 text-stone-200 hover:bg-stone-700"
            >
              Reset to defaults
            </button>
          </div>
          <ul className="mt-3 text-xs text-stone-400 list-disc pl-4 space-y-1">
            {presets.map((p) => (
              <li key={p.name}><strong className="text-stone-200">{p.label}:</strong> {p.description}</li>
            ))}
          </ul>
        </section>

        {/* Trauma ratio */}
        <SectionTraumaRatio draft={draft} defaults={data.defaults} setDraft={setDraft} />

        {/* Base triage distribution */}
        <SectionTriageDist draft={draft} defaults={data.defaults} setDraft={setDraft} />

        {/* MASCAL distribution */}
        <SectionMascalDist draft={draft} defaults={data.defaults} setDraft={setDraft} />

        {/* Threat level shifts */}
        <SectionThreatShift draft={draft} defaults={data.defaults} setDraft={setDraft} />

        {/* Etiology lists */}
        <SectionStringLists
          title="Etiology pool by tactical setting"
          field="etiology_by_setting"
          draft={draft}
          setDraft={setDraft}
          defaults={data.defaults}
          help="Mechanisms sampled for trauma cases. MASCAL day overrides this with mascal_etiology."
        />
        <SectionStringLists
          title="DNBI by region"
          field="dnbi_by_region"
          draft={draft}
          setDraft={setDraft}
          defaults={data.defaults}
          help="Endemic disease patterns added on top of environment DNBI."
        />
        <SectionStringLists
          title="CBRN etiologies"
          field="cbrn_etiologies"
          draft={draft}
          setDraft={setDraft}
          defaults={data.defaults}
          help="Specific CBRN cases sampled when a day has cbrn=true."
        />

        {/* Save */}
        <div className="flex justify-center mt-6 mb-12">
          <button
            onClick={onSave}
            disabled={saving}
            className={`px-8 py-3 rounded-lg font-bold transition-all ${saving ? 'bg-stone-700 text-stone-500' : 'bg-amber-600 hover:bg-amber-500 text-stone-900'}`}
          >
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section components
// ---------------------------------------------------------------------------

function SectionTraumaRatio({
  draft,
  defaults,
  setDraft,
}: {
  draft: MatrixView;
  defaults: MatrixView;
  setDraft: React.Dispatch<React.SetStateAction<MatrixView | null>>;
}) {
  const settings = Object.keys(draft.trauma_ratio_by_setting);
  return (
    <section className="bg-stone-800 border border-stone-700 rounded-lg p-4 mb-6">
      <h2 className="text-amber-400 font-semibold mb-1">Trauma : DNBI ratio per tactical setting</h2>
      <p className="text-xs text-stone-400 mb-3">Fraction of casualties that are trauma. Range 0.0–1.0. Higher = more trauma, less DNBI.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {settings.map((s) => (
          <div key={s} className="flex items-center justify-between gap-3">
            <label className="text-sm">{s}</label>
            <NumberCell
              value={draft.trauma_ratio_by_setting[s]}
              defaultValue={defaults.trauma_ratio_by_setting[s]}
              min={0}
              max={1}
              step={0.05}
              onChange={(v) => setDraft((d) => d && ({ ...d, trauma_ratio_by_setting: { ...d.trauma_ratio_by_setting, [s]: v } }))}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function SectionTriageDist({
  draft,
  defaults,
  setDraft,
}: {
  draft: MatrixView;
  defaults: MatrixView;
  setDraft: React.Dispatch<React.SetStateAction<MatrixView | null>>;
}) {
  const settings = Object.keys(draft.base_triage_distribution);
  return (
    <section className="bg-stone-800 border border-stone-700 rounded-lg p-4 mb-6">
      <h2 className="text-amber-400 font-semibold mb-1">Base triage distribution</h2>
      <p className="text-xs text-stone-400 mb-3">T1/T2/T3/T4 share per tactical setting. Each row must sum to 1.0.</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-stone-400">
              <th className="text-left p-1">Setting</th>
              {TRIAGE.map((t) => <th key={t} className="p-1">{t}</th>)}
              <th className="p-1">Σ</th>
            </tr>
          </thead>
          <tbody>
            {settings.map((s) => {
              const row = draft.base_triage_distribution[s];
              const sum = TRIAGE.reduce((acc, t) => acc + (row[t] || 0), 0);
              const ok = Math.abs(sum - 1) < 0.01;
              return (
                <tr key={s}>
                  <td className="py-1 pr-2">{s}</td>
                  {TRIAGE.map((t) => (
                    <td key={t} className="p-1 text-center">
                      <NumberCell
                        value={row[t] ?? 0}
                        defaultValue={defaults.base_triage_distribution[s]?.[t] ?? 0}
                        min={0} max={1} step={0.05}
                        onChange={(v) => setDraft((d) => {
                          if (!d) return d;
                          return {
                            ...d,
                            base_triage_distribution: {
                              ...d.base_triage_distribution,
                              [s]: { ...d.base_triage_distribution[s], [t]: v },
                            },
                          };
                        })}
                      />
                    </td>
                  ))}
                  <td className={`p-1 text-center font-mono text-xs ${ok ? 'text-stone-400' : 'text-red-400'}`}>
                    {round3(sum)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SectionMascalDist({
  draft,
  defaults,
  setDraft,
}: {
  draft: MatrixView;
  defaults: MatrixView;
  setDraft: React.Dispatch<React.SetStateAction<MatrixView | null>>;
}) {
  const sum = TRIAGE.reduce((acc, t) => acc + (draft.mascal_triage_distribution[t] || 0), 0);
  const ok = Math.abs(sum - 1) < 0.01;
  return (
    <section className="bg-stone-800 border border-stone-700 rounded-lg p-4 mb-6">
      <h2 className="text-amber-400 font-semibold mb-1">MASCAL triage distribution</h2>
      <p className="text-xs text-stone-400 mb-3">Override applied on MASCAL days. Must sum to 1.0.</p>
      <div className="flex items-center gap-4">
        {TRIAGE.map((t) => (
          <div key={t} className="text-center">
            <div className="text-xs text-stone-400 mb-1">{t}</div>
            <NumberCell
              value={draft.mascal_triage_distribution[t] ?? 0}
              defaultValue={defaults.mascal_triage_distribution[t] ?? 0}
              min={0} max={1} step={0.05}
              onChange={(v) => setDraft((d) => d && ({
                ...d,
                mascal_triage_distribution: { ...d.mascal_triage_distribution, [t]: v },
              }))}
            />
          </div>
        ))}
        <div className={`ml-4 text-sm font-mono ${ok ? 'text-stone-400' : 'text-red-400'}`}>Σ {round3(sum)}</div>
      </div>
    </section>
  );
}

function SectionThreatShift({
  draft,
  defaults,
  setDraft,
}: {
  draft: MatrixView;
  defaults: MatrixView;
  setDraft: React.Dispatch<React.SetStateAction<MatrixView | null>>;
}) {
  const levels = Object.keys(draft.threat_level_shift);
  const keys = ['trauma_ratio', 't1_pp', 't2_pp', 't3_pp', 't4_pp'];
  return (
    <section className="bg-stone-800 border border-stone-700 rounded-lg p-4 mb-6">
      <h2 className="text-amber-400 font-semibold mb-1">Threat level shift</h2>
      <p className="text-xs text-stone-400 mb-3">
        Deltas applied per threat level. trauma_ratio adds to the base; t*_pp shifts the triage
        distribution by percentage points (positive shifts severity up).
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-stone-400">
              <th className="text-left p-1">Level</th>
              {keys.map((k) => <th key={k} className="p-1">{k}</th>)}
            </tr>
          </thead>
          <tbody>
            {levels.map((lvl) => (
              <tr key={lvl}>
                <td className="py-1 pr-2">{lvl}</td>
                {keys.map((k) => (
                  <td key={k} className="p-1 text-center">
                    <NumberCell
                      value={draft.threat_level_shift[lvl][k] ?? 0}
                      defaultValue={defaults.threat_level_shift[lvl]?.[k] ?? 0}
                      min={-1} max={1} step={0.01}
                      onChange={(v) => setDraft((d) => d && ({
                        ...d,
                        threat_level_shift: {
                          ...d.threat_level_shift,
                          [lvl]: { ...d.threat_level_shift[lvl], [k]: v },
                        },
                      }))}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SectionStringLists({
  title,
  field,
  draft,
  defaults,
  setDraft,
  help,
}: {
  title: string;
  field: 'etiology_by_setting' | 'dnbi_by_region' | 'cbrn_etiologies';
  draft: MatrixView;
  defaults: MatrixView;
  setDraft: React.Dispatch<React.SetStateAction<MatrixView | null>>;
  help: string;
}) {
  const groups = draft[field];
  const updateGroup = (key: string, items: string[]) => {
    setDraft((d) => d && ({ ...d, [field]: { ...d[field], [key]: items } }));
  };
  return (
    <section className="bg-stone-800 border border-stone-700 rounded-lg p-4 mb-6">
      <h2 className="text-amber-400 font-semibold mb-1">{title}</h2>
      <p className="text-xs text-stone-400 mb-3">{help}</p>
      <div className="space-y-3">
        {Object.keys(groups).map((key) => (
          <div key={key} className="border border-stone-700 rounded p-3">
            <div className="text-sm font-medium mb-2">{key}</div>
            <div className="flex flex-wrap gap-2">
              {groups[key].map((item, idx) => (
                <span key={`${key}-${idx}`} className="bg-stone-700 px-2 py-1 rounded flex items-center gap-2 text-xs">
                  <input
                    className="bg-transparent border-b border-stone-600 focus:border-amber-500 outline-none w-48"
                    value={item}
                    onChange={(e) => {
                      const next = [...groups[key]];
                      next[idx] = e.target.value;
                      updateGroup(key, next);
                    }}
                  />
                  <button
                    onClick={() => updateGroup(key, groups[key].filter((_, i) => i !== idx))}
                    className="text-red-400 hover:text-red-300"
                    aria-label="remove"
                  >×</button>
                </span>
              ))}
              <button
                onClick={() => updateGroup(key, [...groups[key], 'New entry'])}
                className="text-xs px-2 py-1 rounded border border-stone-600 hover:bg-stone-700"
              >
                + Add
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function NumberCell({
  value, defaultValue, min, max, step, onChange,
}: {
  value: number;
  defaultValue: number;
  min: number; max: number; step: number;
  onChange: (n: number) => void;
}) {
  const changed = Math.abs(value - defaultValue) > 1e-6;
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => {
        const v = parseFloat(e.target.value);
        onChange(Number.isFinite(v) ? v : 0);
      }}
      className={`w-20 bg-stone-700 border ${changed ? 'border-amber-500' : 'border-stone-600'} rounded px-2 py-1 text-sm text-right`}
    />
  );
}
