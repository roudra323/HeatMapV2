import type { TimelineBucket } from "@/lib/api";
import { date } from "@/lib/format";

const HEIGHT = 160;

/** Transfers received (up) and sent (down) per period, mirrored around one baseline. */
export function TimelineChart({ buckets }: { buckets: TimelineBucket[] }) {
  if (buckets.length === 0) return <p className="text-sm text-muted">No activity in range.</p>;
  const max = Math.max(1, ...buckets.map((b) => Math.max(b.transfers_in, b.transfers_out)));
  const width = Math.max(320, buckets.length * 10);
  const bar = width / buckets.length;
  const mid = HEIGHT / 2;
  const totalIn = buckets.reduce((s, b) => s + b.transfers_in, 0);
  const totalOut = buckets.reduce((s, b) => s + b.transfers_out, 0);
  const first = buckets[0]!.period;
  const last = buckets.at(-1)!.period;
  return (
    <figure>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${HEIGHT}`}
          className="h-40 w-full min-w-80"
          preserveAspectRatio="none"
          role="img"
          aria-label={`Weekly transfers from ${date(first)} to ${date(last)}: ${totalIn} received, ${totalOut} sent.`}
        >
          <line x1={0} x2={width} y1={mid} y2={mid} stroke="var(--line-strong)" strokeWidth={1} />
          {buckets.map((b, i) => {
            const up = (b.transfers_in / max) * (mid - 6);
            const down = (b.transfers_out / max) * (mid - 6);
            const label = `Week of ${date(b.period)}: ${b.transfers_in} received, ${b.transfers_out} sent`;
            const w = Math.max(1, bar - 2);
            return (
              <g key={b.period}>
                <title>{label}</title>
                <rect x={i * bar} y={0} width={bar} height={HEIGHT} fill="transparent" />
                {up > 0 && <rect x={i * bar + 1} y={mid - up - 1} width={w} height={up} rx={Math.min(2, w / 2)} fill="var(--series-1)" />}
                {down > 0 && <rect x={i * bar + 1} y={mid + 1} width={w} height={down} rx={Math.min(2, w / 2)} fill="var(--series-2)" />}
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: "var(--series-1)" }} />
          Received <span className="num text-ink">{totalIn.toLocaleString("en-US")}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: "var(--series-2)" }} />
          Sent <span className="num text-ink">{totalOut.toLocaleString("en-US")}</span>
        </span>
        <span className="num ml-auto">
          {date(first)} to {date(last)}
        </span>
      </figcaption>
    </figure>
  );
}
