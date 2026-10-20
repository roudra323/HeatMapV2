import type { TimelineBucket } from "@/lib/api";

const HEIGHT = 140;

/** Inbound (up) and outbound (down) transfer counts per period. */
export function TimelineChart({ buckets }: { buckets: TimelineBucket[] }) {
  if (buckets.length === 0) return <p className="text-sm text-muted">No activity in range.</p>;
  const max = Math.max(1, ...buckets.map((b) => Math.max(b.transfers_in, b.transfers_out)));
  const width = Math.max(320, buckets.length * 10);
  const bar = width / buckets.length;
  const mid = HEIGHT / 2;
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${HEIGHT}`} className="h-36 w-full min-w-80" preserveAspectRatio="none" role="img" aria-label="Activity timeline">
        <line x1={0} x2={width} y1={mid} y2={mid} stroke="var(--line)" />
        {buckets.map((b, i) => {
          const up = (b.transfers_in / max) * (mid - 4);
          const down = (b.transfers_out / max) * (mid - 4);
          const label = `${b.period.slice(0, 10)} · in ${b.transfers_in} · out ${b.transfers_out}`;
          return (
            <g key={b.period}>
              <rect x={i * bar + 1} y={mid - up} width={Math.max(1, bar - 2)} height={up} fill="var(--ok)">
                <title>{label}</title>
              </rect>
              <rect x={i * bar + 1} y={mid} width={Math.max(1, bar - 2)} height={down} fill="var(--accent)">
                <title>{label}</title>
              </rect>
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex gap-3 text-xs text-muted">
        <span><span className="text-ok">■</span> inbound</span>
        <span><span className="text-accent">■</span> outbound</span>
      </div>
    </div>
  );
}
