"use client";

import { useRouter } from "next/navigation";

import type { ClusterPoint } from "@/lib/api";
import { shortAddress } from "@/lib/format";

const SERIES = 8;

/** Fixed colour per cluster id (never by rank); noise is grey. */
export function clusterColor(id: number): string {
  return id < 0 ? "var(--series-none)" : `var(--series-${(id % SERIES) + 1})`;
}

/**
 * 2-D projection of wallet behaviour, coloured by cluster. Selecting a cluster
 * fades the others so its members stand out.
 */
export function ClusterScatter({ points, selected }: { points: ClusterPoint[]; selected?: number | null }) {
  const router = useRouter();
  if (points.length === 0) return <p className="text-sm text-muted">No wallets have been projected yet.</p>;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (x: number) => 20 + ((x - minX) / (maxX - minX || 1)) * 660;
  const sy = (y: number) => 380 - ((y - minY) / (maxY - minY || 1)) * 360;
  const hasSelection = selected !== null && selected !== undefined;
  // Draw the selected cluster last so it sits on top.
  const ordered = hasSelection
    ? [...points.filter((p) => p.cluster_id !== selected), ...points.filter((p) => p.cluster_id === selected)]
    : points;
  return (
    <svg
      viewBox="0 0 700 400"
      className="h-auto w-full"
      role="img"
      aria-label={`Behaviour map of ${points.length} wallets. Use the cluster list to explore members.`}
    >
      <rect x={0} y={0} width={700} height={400} rx={8} fill="var(--surface-2)" />
      {ordered.map((p) => {
        const dim = hasSelection && p.cluster_id !== selected;
        return (
          <circle
            key={p.address}
            cx={sx(p.x)}
            cy={sy(p.y)}
            r={hasSelection && !dim ? 5 : 4}
            fill={dim ? "var(--line-strong)" : clusterColor(p.cluster_id)}
            fillOpacity={dim ? 0.5 : 0.45 + 0.55 * (p.probability ?? 1)}
            stroke="var(--surface)"
            strokeWidth={1}
            className="cursor-pointer"
            onClick={() => router.push(`/wallets/${p.address}`)}
          >
            <title>{`${shortAddress(p.address)}: ${p.cluster_id < 0 ? "no cluster" : `cluster ${p.cluster_id}`}`}</title>
          </circle>
        );
      })}
    </svg>
  );
}
