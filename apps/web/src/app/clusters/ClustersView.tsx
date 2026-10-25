"use client";

import Link from "next/link";
import { useState } from "react";

import { ClusterScatter, clusterColor } from "@/components/ClusterScatter";
import { HeatGrid } from "@/components/HeatGrid";
import { ScatterIcon } from "@/components/icons";
import { AddressLink, Async, buttonClass, EmptyState, PageHeader, Panel, Skeleton, SkeletonRows } from "@/components/ui";
import type { Cluster, ClusterPoint, Heatmap } from "@/lib/api";
import { date, num, pct, sentence } from "@/lib/format";
import { useApi } from "@/lib/useApi";

function clusterName(c: Pick<Cluster, "cluster_id" | "label">): string {
  return c.cluster_id < 0 ? "Unclustered" : sentence(c.label);
}

export function ClustersView() {
  const clusters = useApi<Cluster[]>("/v1/clusters");
  const points = useApi<ClusterPoint[]>("/v1/clusters/points");
  const segments = useApi<Heatmap>("/v1/heatmaps/segments", { by: "cluster" });
  const [selected, setSelected] = useState<number | null>(null);

  const real = clusters.data?.filter((c) => c.cluster_id >= 0) ?? [];
  const noise = clusters.data?.find((c) => c.cluster_id < 0);
  const current = clusters.data?.find((c) => c.cluster_id === selected);
  const members = selected === null ? [] : (points.data ?? []).filter((p) => p.cluster_id === selected);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Clusters"
        description="Tracked wallets grouped by how they behave: what they hold, where they trade and how often. Each cluster is a candidate audience segment. Pick one to see who is in it."
        actions={
          clusters.data?.[0] ? (
            <p className="text-[0.8125rem] text-muted">Model run {date(clusters.data[0].snapshot_at)}</p>
          ) : undefined
        }
      />

      <Async
        state={clusters}
        skeleton={<Skeleton className="h-96 w-full" />}
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState
            icon={<ScatterIcon size={22} />}
            title="No clusters yet"
            action={
              <>
                <Link href="/watchlist" className={buttonClass("primary", "sm")}>
                  Open the watchlist
                </Link>
                <Link href="/discover" className={buttonClass("secondary", "sm")}>
                  Discover traders
                </Link>
              </>
            }
          >
            Clusters are built by the models job from tracked wallets that have a behaviour snapshot. Track wallets, let
            their history sync, then run the models job.
          </EmptyState>
        }
      >
        {() => (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <Panel
                title="Behaviour map"
                description="Each dot is a wallet; wallets that behave alike sit close together. Fainter dots fit their cluster less well."
              >
                <Async state={points} skeleton={<Skeleton className="aspect-[7/4] w-full" />}>
                  {(d) => <ClusterScatter points={d} selected={selected} />}
                </Async>
              </Panel>
            </div>
            <Panel title={`${real.length} clusters`} description={noise ? `${num(noise.size)} wallets fit no cluster.` : undefined}>
              <ul className="-mx-2 space-y-1">
                {real.map((c) => {
                  const active = c.cluster_id === selected;
                  return (
                    <li key={c.label}>
                      <button
                        type="button"
                        aria-pressed={active}
                        onClick={() => setSelected(active ? null : c.cluster_id)}
                        className={`flex w-full gap-3 rounded-md px-2 py-2 text-left transition-colors duration-150 ${
                          active ? "bg-primary-soft" : "hover:bg-surface-2"
                        }`}
                      >
                        <span aria-hidden="true" className="mt-1 h-3 w-3 shrink-0 rounded-full" style={{ background: clusterColor(c.cluster_id) }} />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-baseline justify-between gap-2">
                            <span className="text-sm font-medium">{clusterName(c)}</span>
                            <span className="num text-xs text-muted">{num(c.size)} wallets</span>
                          </span>
                          {c.profile && <span className="mt-0.5 block text-[0.8125rem] leading-snug text-muted">{c.profile}</span>}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Panel>
          </div>
        )}
      </Async>

      {current && (
        <Panel
          title={`Members of ${clusterName(current).toLowerCase()}`}
          description={current.profile ?? undefined}
          action={
            <button type="button" className={buttonClass("ghost", "sm")} onClick={() => setSelected(null)}>
              Clear selection
            </button>
          }
        >
          {members.length === 0 ? (
            <p className="text-sm text-muted">No members in the current projection.</p>
          ) : (
            <ul className="grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3">
              {members
                .slice()
                .sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))
                .map((m) => (
                  <li key={m.address} className="flex items-center justify-between gap-3 border-b border-line py-2 text-sm">
                    <AddressLink address={m.address} />
                    {m.probability !== null && <span className="num text-xs text-muted">{pct(m.probability)} fit</span>}
                  </li>
                ))}
            </ul>
          )}
        </Panel>
      )}

      {(clusters.data?.length ?? 0) > 0 && (
        <Panel
          title="What each cluster moves and uses"
          description="Share of each cluster's transfers by asset type and destination. Darker means a larger share."
        >
          <Async
            state={segments}
            skeleton={<SkeletonRows rows={6} />}
            isEmpty={(h) => h.rows.length === 0}
            empty={<p className="text-sm text-muted">No segment data for this model run.</p>}
          >
            {(h) => <HeatGrid heatmap={h} format={pct} rowLabel={(r) => sentence(r)} />}
          </Async>
        </Panel>
      )}
    </div>
  );
}
