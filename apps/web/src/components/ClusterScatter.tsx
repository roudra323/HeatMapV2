"use client";

import { useRouter } from "next/navigation";

import type { ClusterPoint } from "@/lib/api";

const PALETTE = ["#c2410c", "#0f766e", "#7c3aed", "#b45309", "#2563eb", "#be123c", "#4d7c0f", "#0e7490"];

export function clusterColor(id: number): string {
  return id < 0 ? "var(--muted)" : PALETTE[id % PALETTE.length]!;
}

/** 2-D projection of wallet behaviour, coloured by cluster (grey = noise). */
export function ClusterScatter({ points }: { points: ClusterPoint[] }) {
  const router = useRouter();
  if (points.length === 0) return <p className="text-sm text-muted">Run the models job to see clusters.</p>;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (x: number) => 20 + ((x - minX) / (maxX - minX || 1)) * 660;
  const sy = (y: number) => 380 - ((y - minY) / (maxY - minY || 1)) * 360;
  return (
    <svg viewBox="0 0 700 400" className="h-auto w-full" role="img" aria-label="Behaviour clusters">
      {points.map((p) => (
        <circle
          key={p.address}
          cx={sx(p.x)}
          cy={sy(p.y)}
          r={4}
          fill={clusterColor(p.cluster_id)}
          fillOpacity={0.4 + 0.6 * (p.probability ?? 1)}
          className="cursor-pointer"
          onClick={() => router.push(`/wallets/${p.address}`)}
        >
          <title>{`${p.address}\ncluster ${p.cluster_id < 0 ? "noise" : p.cluster_id}`}</title>
        </circle>
      ))}
    </svg>
  );
}
