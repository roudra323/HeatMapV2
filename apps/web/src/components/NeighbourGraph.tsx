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
import { sentence, shortAddress } from "@/lib/format";

import { AddressLink, Badge } from "./ui";

type SimNode = SimulationNodeDatum & NetworkNode;
type SimLink = SimulationLinkDatum<SimNode> & { weight: number };

const WIDTH = 720;
const HEIGHT = 440;

const KINDS = [
  { key: "center", color: "var(--ink)", label: "This wallet" },
  { key: "tracked", color: "var(--primary)", label: "Tracked" },
  { key: "hub", color: "var(--series-none)", label: "Hub (exchange, router; not expanded)" },
  { key: "other", color: "var(--surface)", label: "Not tracked" },
] as const;

function kind(node: NetworkNode): (typeof KINDS)[number] {
  if (node.depth === 0) return KINDS[0];
  if (node.is_hub) return KINDS[2];
  if (node.tracked) return KINDS[1];
  return KINDS[3];
}

function describe(n: NetworkNode): string {
  const name = n.label ?? shortAddress(n.address);
  const what = n.category ? sentence(n.category) : n.tracked ? `tracked, hop ${n.hop}` : "not tracked";
  return `${name}, ${what}`;
}

/** Force-directed ego network, with a ranked list of the same neighbours underneath. */
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
    const links: SimLink[] = [...weights.entries()]
      .map(([key, weight]) => {
        const [a, b] = key.split("|") as [string, string];
        return { source: byId.get(a)!, target: byId.get(b)!, weight };
      })
      .filter((l) => l.source && l.target);
    const sim = forceSimulation(nodes)
      .force("link", forceLink<SimNode, SimLink>(links).distance((l) => 60 + 120 / Math.sqrt(l.weight)))
      .force("charge", forceManyBody().strength(-170))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", forceCollide(15))
      .stop();
    for (let i = 0; i < 300; i++) sim.tick();
    for (const n of nodes) {
      n.x = Math.max(16, Math.min(WIDTH - 16, n.x ?? 0));
      n.y = Math.max(20, Math.min(HEIGHT - 12, n.y ?? 0));
    }
    const maxWeight = Math.max(1, ...links.map((l) => l.weight));
    // Strength of each node's tie to the centre, for the ranked list.
    const centre = network.center;
    const ties = new Map<string, number>();
    for (const l of links) {
      const s = (l.source as SimNode).address;
      const t = (l.target as SimNode).address;
      if (s === centre) ties.set(t, (ties.get(t) ?? 0) + l.weight);
      else if (t === centre) ties.set(s, (ties.get(s) ?? 0) + l.weight);
    }
    const ranked = nodes
      .filter((n) => n.depth > 0)
      .map((n) => ({ node: n, weight: ties.get(n.address) ?? 0 }))
      .sort((a, b) => b.weight - a.weight);
    return { nodes, links, maxWeight, ranked };
  }, [network]);

  if (network.nodes.length <= 1) return <p className="text-sm text-muted">No neighbours yet.</p>;

  const open = (address: string) => router.push(`/wallets/${address}`);

  return (
    <div className="space-y-4">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="group" aria-label="Neighbour network">
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
              strokeWidth={0.75 + 3 * (l.weight / layout.maxWeight)}
            >
              <title>{`${l.weight} transfers`}</title>
            </line>
          );
        })}
        {layout.nodes.map((n) => {
          const k = kind(n);
          const r = n.depth === 0 ? 10 : n.is_hub ? 8 : 6.5;
          return (
            <g
              key={n.address}
              transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
              className="cursor-pointer outline-none [&:focus-visible>circle:first-child]:stroke-[var(--focus)]"
              role="link"
              tabIndex={0}
              aria-label={`Open ${describe(n)}`}
              onClick={() => open(n.address)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  open(n.address);
                }
              }}
            >
              <circle r={r + 5} fill="transparent" stroke="transparent" strokeWidth={2} />
              <circle r={r} fill={k.color} stroke={k.key === "other" ? "var(--muted)" : "var(--surface)"} strokeWidth={1.5} />
              {(n.depth === 0 || n.label || n.tracked) && (
                <text
                  y={-r - 5}
                  textAnchor="middle"
                  fontSize={11}
                  fill="var(--ink)"
                  stroke="var(--surface)"
                  strokeWidth={3}
                  paintOrder="stroke"
                  className={n.label ? "" : "mono"}
                >
                  {n.label ?? shortAddress(n.address)}
                </text>
              )}
              <title>{describe(n)}</title>
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {KINDS.map((k) => (
          <span key={k.key} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: k.color, boxShadow: k.key === "other" ? "inset 0 0 0 1.5px var(--muted)" : undefined }}
            />
            {k.label}
          </span>
        ))}
      </div>
      <details className="group">
        <summary className="inline-flex min-h-9 items-center text-[0.8125rem] font-medium text-primary">
          List neighbours by number of transfers ({layout.ranked.length})
        </summary>
        <ol className="mt-2 divide-y divide-line">
          {layout.ranked.map(({ node, weight }) => (
            <li key={node.address} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span className="flex flex-wrap items-center gap-2">
                <AddressLink address={node.address} label={node.label} />
                {node.category && <Badge>{sentence(node.category)}</Badge>}
                {node.tracked && <Badge tone="primary">Tracked</Badge>}
                {node.depth > 1 && <Badge>2nd hop</Badge>}
              </span>
              <span className="num text-muted">{weight > 0 ? `${weight.toLocaleString("en-US")} transfers` : "indirect"}</span>
            </li>
          ))}
        </ol>
      </details>
    </div>
  );
}
