"use client";

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

import type { Network, NetworkNode } from "@/lib/api";
import { shortAddress } from "@/lib/format";

type SimNode = SimulationNodeDatum & NetworkNode;
type SimLink = SimulationLinkDatum<SimNode> & { weight: number };

const WIDTH = 720;
const HEIGHT = 440;

function color(node: NetworkNode): string {
  if (node.depth === 0) return "var(--accent)";
  if (node.is_hub) return "var(--muted)";
  if (node.tracked) return "var(--ok)";
  return "var(--line)";
}

/** Force-directed ego network. Hubs are grey, tracked wallets green, the centre orange. */
export function NeighbourGraph({ network }: { network: Network }) {
  const router = useRouter();
  const layout = useMemo(() => {
    const nodes: SimNode[] = network.nodes.map((n) => ({ ...n }));
    const byId = new Map(nodes.map((n) => [n.address, n]));
    const weights = new Map<string, number>();
    for (const e of network.edges) {
      const key = [e.src, e.dst].sort().join("|");
      weights.set(key, (weights.get(key) ?? 0) + e.tx_count);
    }
    const links: SimLink[] = [...weights.entries()].map(([key, weight]) => {
      const [a, b] = key.split("|") as [string, string];
      return { source: byId.get(a)!, target: byId.get(b)!, weight };
    });
    const sim = forceSimulation(nodes)
      .force("link", forceLink<SimNode, SimLink>(links).distance((l) => 60 + 120 / Math.sqrt(l.weight)))
      .force("charge", forceManyBody().strength(-160))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", forceCollide(14))
      .stop();
    for (let i = 0; i < 300; i++) sim.tick();
    const maxWeight = Math.max(1, ...links.map((l) => l.weight));
    return { nodes, links, maxWeight };
  }, [network]);

  if (network.nodes.length <= 1) return <p className="text-sm text-muted">No neighbours yet.</p>;

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="Neighbour network">
        {layout.links.map((l, i) => {
          const s = l.source as SimNode;
          const t = l.target as SimNode;
          return (
            <line
              key={i}
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              stroke="var(--muted)"
              strokeOpacity={0.35}
              strokeWidth={0.5 + 3 * (l.weight / layout.maxWeight)}
            >
              <title>{`${l.weight} transfers`}</title>
            </line>
          );
        })}
        {layout.nodes.map((n) => (
          <g
            key={n.address}
            transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
            className="cursor-pointer"
            onClick={() => router.push(`/wallets/${n.address}`)}
          >
            <circle r={n.depth === 0 ? 10 : n.is_hub ? 8 : 6} fill={color(n)} stroke="var(--panel)" strokeWidth={1.5} />
            {(n.depth === 0 || n.label || n.tracked) && (
              <text y={-12} textAnchor="middle" fontSize={10} fill="var(--ink)">
                {n.label ?? shortAddress(n.address)}
              </text>
            )}
            <title>
              {`${n.label ?? n.address}\n${n.category ?? (n.tracked ? `tracked · hop ${n.hop}` : "untracked")}`}
            </title>
          </g>
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted">
        {[
          ["var(--accent)", "this wallet"],
          ["var(--ok)", "tracked"],
          ["var(--muted)", "hub (not expanded)"],
          ["var(--line)", "other"],
        ].map(([c, label]) => (
          <span key={label} className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
