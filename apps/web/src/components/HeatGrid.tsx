"use client";

import { useState } from "react";

import type { Heatmap } from "@/lib/api";
import { humanize } from "@/lib/format";

const LEVELS = ["var(--heat-0)", "var(--heat-1)", "var(--heat-2)", "var(--heat-3)", "var(--heat-4)"];

function level(value: number, max: number): string {
  if (max <= 0 || value <= 0) return LEVELS[0]!;
  const idx = Math.min(4, 1 + Math.floor((value / max) * 3.999));
  return LEVELS[idx]!;
}

/** Generic matrix heatmap: rows × columns with a five-step sequential scale. */
export function HeatGrid({
  heatmap,
  format = (v) => String(v),
  rowLabel = (r) => r,
  columnLabel = (c) => humanize(c),
}: {
  heatmap: Heatmap;
  format?: (v: number) => string;
  rowLabel?: (r: string) => string;
  columnLabel?: (c: string) => string;
}) {
  const [hover, setHover] = useState<string>();
  const max = Math.max(0, ...heatmap.values.flat());
  if (heatmap.rows.length === 0) return <p className="text-sm text-muted">No data yet.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-96 table-fixed border-separate border-spacing-0.5 text-xs">
        <colgroup>
          <col className="w-24" />
        </colgroup>
        <thead>
          <tr>
            <th />
            {heatmap.columns.map((c) => (
              <th key={c} className="px-0.5 align-bottom font-normal text-muted">
                <div className="max-h-24 whitespace-nowrap [writing-mode:vertical-rl] rotate-180">
                  {columnLabel(c)}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {heatmap.rows.map((row, i) => (
            <tr key={row}>
              <th className="truncate pr-2 text-right font-normal text-muted" title={rowLabel(row)}>
                {rowLabel(row)}
              </th>
              {heatmap.columns.map((col, j) => {
                const v = heatmap.values[i]?.[j] ?? 0;
                return (
                  <td
                    key={col}
                    className="h-5 rounded-sm"
                    style={{ background: level(v, max) }}
                    title={`${rowLabel(row)} · ${columnLabel(col)}: ${format(v)}`}
                    onMouseEnter={() => setHover(`${rowLabel(row)} · ${columnLabel(col)}: ${format(v)}`)}
                    onMouseLeave={() => setHover(undefined)}
                  />
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-3 text-xs text-muted">
        <span className="flex items-center gap-1">
          less
          {LEVELS.map((l) => (
            <span key={l} className="inline-block h-3 w-3 rounded-sm" style={{ background: l }} />
          ))}
          more
        </span>
        <span className="mono">{hover ?? " "}</span>
      </div>
    </div>
  );
}
