// Shared types + pure helpers for the controller layer (see backend/scenario.py).

export interface Vitals {
  t: number;
  hr?: number | null;
  sbp?: number | null;
  dbp?: number | null;
  rr?: number | null;
  spo2?: number | null;
  temp_f?: number | null;
  etco2?: number | null;
  avpu?: string | null;
  gcs_e?: number | null;
  gcs_v?: number | null;
  gcs_m?: number | null;
  pupils?: string | null;
}

export interface TreeNode {
  id: string;
  type?: string;
  label?: string;
  detail?: string;
  failure?: boolean;
}

export interface TreeEdge {
  from: string;
  to: string;
  condition?: string;
}

export interface Leg {
  leg_id: string;
  title: string;
  focus: boolean;
  capability: string[];
  handover?: {
    summary?: string;
    vitals?: Partial<Vitals>;
    meds?: { drug?: string; dose?: string; route?: string; minutes_prior?: number }[];
    interventions?: string[];
  };
  tree: { nodes: TreeNode[]; edges: TreeEdge[] };
  considerations?: string[];
}

export interface CriticalAction {
  id: string;
  leg_id: string;
  action: string;
  window_min?: number;
  if_missed?: string;
  rejoin?: string;
}

export interface Finding {
  severity: 'high' | 'medium' | 'low';
  category: string;
  location: string;
  issue: string;
  fix: string;
  source: string;
}

export interface Controller {
  pathway: string;
  chain: { nodes: { id: string; name: string; capability: string[] }[]; fragos: number[]; notes: string[] };
  wounds: { id: string; region: string; side: string; surface: string; type: string; intervention: string; effective?: boolean | null }[];
  moulage?: string;
  critical_decisions?: string[];
  legs: Leg[];
  critical_actions: CriticalAction[];
  vitals_tracks: { green: Vitals[]; red: Vitals[] };
  controller_note?: string;
  focus_leg: string;
  red_team?: { counts: Record<string, number>; open: Finding[]; status: string };
  _fallback?: boolean;
}

export interface CaseRecord {
  meta?: { title?: string };
  zmist?: Record<string, string>;
  triage_category?: string;
  disposition?: string;
  patient_data?: Record<string, string>;
  controller?: Controller;
}

export interface ExportedCase {
  case_num: number;
  day?: number | null;
  arrival?: string | null;
  event?: string | null;
  case: CaseRecord;
}

export interface CasesExport {
  format: string;
  exercise: string;
  fragos: { number: number; day: number; start: number; end: number; title: string; execution: string }[];
  cases: ExportedCase[];
}

export const PATHWAY_LABELS: Record<string, string> = {
  DCR_DCS: 'DCR → DCS → evac',
  DCR_DEFERRED_DCS: 'DCR + PCC → priority evac to surgery',
  DCR_HOLD: 'DCR → holding → evac',
  DCR_PCC: 'DCR → prolonged care (evac denied)',
  MEDICAL: 'Medical → disposition',
  EXPECTANT: 'Expectant',
};

/** Last point at or before minute `m` (tracks are sorted by t). */
export function pointAt(track: Vitals[], m: number): Vitals | null {
  if (!track.length) return null;
  let cur = track[0];
  for (const p of track) {
    if ((p.t ?? 0) <= m) cur = p;
    else break;
  }
  return cur;
}

export function nextChange(track: Vitals[], m: number): number | null {
  const nxt = track.find(p => (p.t ?? 0) > m);
  return nxt ? nxt.t : null;
}

export function gcsTotal(v: Vitals | null): number | null {
  if (!v || v.gcs_e == null || v.gcs_v == null || v.gcs_m == null) return null;
  return v.gcs_e + v.gcs_v + v.gcs_m;
}

/** Column = BFS depth from the first node; rows ordered by parents' mean row.
 * Mirrors controller_docs._layout so the screen matches the printed packet. */
export function layoutTree(nodes: TreeNode[], edges: TreeEdge[]): Record<string, [number, number]> {
  const ids = nodes.map(n => n.id);
  const adj: Record<string, string[]> = {};
  for (const e of edges) (adj[e.from] ||= []).push(e.to);
  const depth: Record<string, number> = {};
  if (ids.length) depth[ids[0]] = 0;
  const q = ids.slice(0, 1);
  while (q.length) {
    const n = q.shift()!;
    for (const m of adj[n] || []) {
      if (ids.includes(m) && depth[m] === undefined) {
        depth[m] = depth[n] + 1;
        q.push(m);
      }
    }
  }
  const trailing = Math.max(-1, ...Object.values(depth)) + 1;
  for (const i of ids) if (depth[i] === undefined) depth[i] = trailing;
  const preds: Record<string, string[]> = {};
  for (const e of edges) {
    if (depth[e.from] !== undefined && depth[e.to] !== undefined && depth[e.from] < depth[e.to]) {
      (preds[e.to] ||= []).push(e.from);
    }
  }
  const pos: Record<string, [number, number]> = {};
  const order: Record<string, number> = {};
  ids.forEach((id, k) => (order[id] = k));
  const maxCol = Math.max(-1, ...Object.values(depth));
  for (let c = 0; c <= maxCol; c++) {
    const col = ids.filter(i => depth[i] === c);
    const key = (i: string) => {
      const ps = (preds[i] || []).filter(p => pos[p]).map(p => pos[p][1]);
      return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : 0;
    };
    col.sort((a, b) => key(a) - key(b) || order[a] - order[b]);
    col.forEach((id, r) => (pos[id] = [c, r]));
  }
  return pos;
}

export function fromExercise(ex: { name: string; cases: CaseRecord[]; msel_data?: Record<string, unknown>[]; fragos?: CasesExport['fragos'] }): CasesExport {
  const rows = (ex.msel_data || []).filter(r => 'arr_raw' in r);
  return {
    format: 'role2builder.cases.v1',
    exercise: ex.name,
    fragos: ex.fragos || [],
    cases: (ex.cases || []).map((c, i) => ({
      case_num: i + 1,
      day: (rows[i]?.day as number) ?? null,
      arrival: (rows[i]?.time as string) ?? null,
      event: (rows[i]?.event as string) ?? null,
      case: c,
    })),
  };
}
