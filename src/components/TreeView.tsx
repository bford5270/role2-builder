'use client';

import React from 'react';
import { layoutTree, type Leg } from '@/lib/controller';

const CW = 190;
const RH = 96;
const BW = 164;
const BH = 70;

function wrap(text: string, width = 26, maxLines = 5): string[] {
  const words = (text || '').split(/\s+/);
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    if ((cur + ' ' + w).trim().length > width) {
      if (cur) lines.push(cur);
      cur = w;
    } else {
      cur = (cur + ' ' + w).trim();
    }
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    kept[maxLines - 1] += '…';
    return kept;
  }
  return lines;
}

/** Decision tree as SVG. Clicking a node toggles it as "reached" — the path
 * the team actually took, which feeds the debrief log. */
export default function TreeView({ leg, reached, onToggle }: {
  leg: Leg;
  reached: Set<string>;
  onToggle?: (nodeId: string) => void;
}) {
  const { nodes, edges } = leg.tree || { nodes: [], edges: [] };
  if (!nodes.length) return <p className="text-ink-3 text-sm">No tree for this leg.</p>;
  const pos = layoutTree(nodes, edges);
  const cols = Math.max(...Object.values(pos).map(p => p[0])) + 1;
  const rows = Math.max(...Object.values(pos).map(p => p[1])) + 1;
  const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
  const center = (id: string) => {
    const [c, r] = pos[id];
    return [c * CW + CW / 2, r * RH + RH / 2];
  };

  return (
    <div className="overflow-x-auto">
      <svg width={cols * CW} height={rows * RH + 10} role="img" aria-label={`Decision tree: ${leg.title}`}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--color-ink-3)" />
          </marker>
          <marker id="arrow-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--color-signal-red)" />
          </marker>
        </defs>
        {edges.map((e, k) => {
          if (!pos[e.from] || !pos[e.to]) return null;
          const [x1, y1] = center(e.from);
          const [x2, y2] = center(e.to);
          const fail = byId[e.from]?.failure || byId[e.to]?.failure;
          const sameCol = pos[e.from][0] === pos[e.to][0];
          const back = pos[e.to][0] < pos[e.from][0] || (sameCol && pos[e.to][1] < pos[e.from][1]);
          let d: string;
          if (sameCol && !back) d = `M${x1},${y1 + BH / 2} L${x2},${y2 - BH / 2}`;
          else if (back) d = `M${x1},${y1 + BH / 2} C${x1},${y1 + BH} ${x2},${y2 + BH} ${x2},${y2 + BH / 2}`;
          else d = `M${x1 + BW / 2},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2 - BW / 2},${y2}`;
          const colour = fail ? 'var(--color-signal-red)' : 'var(--color-ink-3)';
          return (
            <g key={k}>
              <path d={d} fill="none" stroke={colour} strokeWidth={1.2} markerEnd={`url(#${fail ? 'arrow-red' : 'arrow'})`} />
              {e.condition && (
                <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 4} fontSize={9} textAnchor="middle" fill={colour}>
                  {e.condition.slice(0, 28)}
                </text>
              )}
            </g>
          );
        })}
        {nodes.map(n => {
          const [x, y] = center(n.id);
          const fail = !!n.failure;
          const outcome = n.type === 'outcome';
          const on = reached.has(n.id);
          const label = outcome && n.detail ? `${n.label} — ${n.detail}` : n.label || '';
          const lines = wrap(label);
          return (
            <g key={n.id} onClick={() => onToggle?.(n.id)} style={{ cursor: onToggle ? 'pointer' : 'default' }}>
              <title>{[n.label, n.detail].filter(Boolean).join('\n')}</title>
              <rect
                x={x - BW / 2} y={y - BH / 2} width={BW} height={BH} rx={3}
                fill={on ? 'var(--color-surface-3)' : 'var(--color-surface-1)'}
                stroke={fail ? 'var(--color-signal-red)' : on ? 'var(--color-accent)' : 'var(--color-border-2)'}
                strokeWidth={outcome || on ? 2.2 : 1}
              />
              {lines.map((ln, i) => (
                <text
                  key={i} x={x} y={y - ((lines.length - 1) * 12) / 2 + i * 12 + 4}
                  fontSize={outcome ? 11 : 10} fontWeight={outcome ? 700 : 400} textAnchor="middle"
                  fill={fail ? 'var(--color-signal-red)' : 'var(--color-ink-1)'}
                >
                  {ln}
                </text>
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
