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

/** Rows × columns on a single-hue heat scale. Hover or focus a cell to read its value. */
export function HeatGrid({
  heatmap,
  format = (v) => String(v),
  rowLabel = (r) => r,
  columnLabel = (c) => humanize(c),
  compact = false,
}: {
  heatmap: Heatmap;
  format?: (v: number) => string;
  rowLabel?: (r: string) => string;
  columnLabel?: (c: string) => string;
  /** Short column labels (hours) instead of rotated category names. */
  compact?: boolean;
}) {
  const [hover, setHover] = useState<string>();
  const max = Math.max(0, ...heatmap.values.flat());
  if (heatmap.rows.length === 0) return <p className="text-sm text-muted">No data yet.</p>;

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[22rem] table-fixed border-separate border-spacing-[2px] text-xs">
          <colgroup>
            <col className={compact ? "w-10" : "w-28"} />
          </colgroup>
          <thead>
            <tr>
              <td />
              {heatmap.columns.map((c, j) => (
                <th key={c} scope="col" className="px-0 pb-1 align-bottom font-normal text-muted">
                  {compact ? (
                    <span className={`num block text-center text-[0.6875rem] ${j % 3 === 0 ? "" : "invisible"}`}>{columnLabel(c)}</span>
                  ) : (
                    <span className="mx-auto block max-h-28 rotate-180 whitespace-nowrap [writing-mode:vertical-rl]">{columnLabel(c)}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {heatmap.rows.map((row, i) => (
              <tr key={row}>
                <th scope="row" className="truncate pr-2 text-right font-normal text-muted" title={rowLabel(row)}>
                  {rowLabel(row)}
                </th>
                {heatmap.columns.map((col, j) => {
                  const v = heatmap.values[i]?.[j] ?? 0;
                  const text = `${rowLabel(row)}, ${columnLabel(col)}: ${format(v)}`;
                  return (
                    <td
                      key={col}
                      className={`${compact ? "h-5" : "h-6"} rounded-[3px] p-0`}
                      style={{ background: level(v, max) }}
                      title={text}
                      onMouseEnter={() => setHover(text)}
                      onMouseLeave={() => setHover(undefined)}
                    >
                      <span className="sr-only">{format(v)}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1">
          Less
          {LEVELS.map((l) => (
            <span key={l} className="inline-block h-3 w-3 rounded-[3px]" style={{ background: l }} />
          ))}
          More
        </span>
        <span className="num min-h-4 text-ink" aria-live="polite">
          {hover ?? ""}
        </span>
      </div>
    </div>
  );
}
