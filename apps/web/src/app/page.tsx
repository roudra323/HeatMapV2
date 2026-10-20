"use client";

import Link from "next/link";

import { AddWalletForm } from "@/components/AddWalletForm";
import { HeatGrid } from "@/components/HeatGrid";
import { Chip, Panel, Stat, State } from "@/components/ui";
import type { Cluster, Heatmap, WatchPage } from "@/lib/api";
import { pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function Overview() {
  const seeds = useApi<WatchPage>("/v1/watchlist", { origin: "seed", limit: 1 });
  const neighbours = useApi<WatchPage>("/v1/watchlist", { origin: "neighbour", limit: 1 });
  const tags = useApi<Record<string, number>>("/v1/tags");
  const clusters = useApi<Cluster[]>("/v1/clusters");
  const segments = useApi<Heatmap>("/v1/heatmaps/segments", { by: "tag" });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-sm text-muted">
          Tracked wallets, the neighbours discovered around them, and how they behave.
        </p>
      </div>

      <Panel title="Track a wallet">
        <AddWalletForm
          onAdded={() => {
            seeds.reload();
          }}
        />
      </Panel>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Seed wallets" value={seeds.data?.total ?? "—"} />
        <Stat label="Discovered neighbours" value={neighbours.data?.total ?? "—"} />
        <Stat label="Behaviour clusters" value={clusters.data?.filter((c) => c.cluster_id >= 0).length ?? "—"} />
        <Stat label="Distinct tags" value={tags.data ? Object.keys(tags.data).length : "—"} />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Panel title="Tags">
          <State loading={tags.loading} error={tags.error} empty={tags.data && Object.keys(tags.data).length === 0 ? "No tags yet." : undefined} />
          <div className="flex flex-wrap gap-2">
            {Object.entries(tags.data ?? {}).map(([tag, n]) => (
              <Chip key={tag} tone={tag === "sybil_suspect" || tag === "mixer_exposure" ? "danger" : "default"}>
                {tag.replaceAll("_", " ")} · {n}
              </Chip>
            ))}
          </div>
        </Panel>
        <div className="md:col-span-2">
          <Panel title="Behaviour by tag" action={<Link href="/clusters" className="text-xs text-accent">clusters →</Link>}>
            <State loading={segments.loading} error={segments.error} />
            {segments.data && <HeatGrid heatmap={segments.data} format={pct} rowLabel={(r) => r.replaceAll("_", " ")} />}
          </Panel>
        </div>
      </div>
    </div>
  );
}
