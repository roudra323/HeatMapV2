"use client";

import { ClusterScatter, clusterColor } from "@/components/ClusterScatter";
import { HeatGrid } from "@/components/HeatGrid";
import { Panel, State } from "@/components/ui";
import type { Cluster, ClusterPoint, Heatmap } from "@/lib/api";
import { pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function ClustersPage() {
  const clusters = useApi<Cluster[]>("/v1/clusters");
  const points = useApi<ClusterPoint[]>("/v1/clusters/points");
  const segments = useApi<Heatmap>("/v1/heatmaps/segments", { by: "cluster" });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Behaviour clusters</h1>
        <p className="text-sm text-muted">
          Wallets grouped by HDBSCAN on their latest feature snapshot. Click a point to open the
          wallet.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="md:col-span-2">
          <Panel title="Projection">
            <State loading={points.loading} error={points.error} />
            {points.data && <ClusterScatter points={points.data} />}
          </Panel>
        </div>
        <Panel title="Clusters">
          <State
            loading={clusters.loading}
            error={clusters.error}
            empty={clusters.data?.length === 0 ? "No model run yet." : undefined}
          />
          <ul className="space-y-2 text-sm">
            {clusters.data?.map((c) => (
              <li key={c.label} className="flex gap-2">
                <span
                  className="mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: clusterColor(c.cluster_id) }}
                />
                <div>
                  <div>
                    {c.label.replace("_", " ")} <span className="mono text-muted">· {c.size}</span>
                  </div>
                  {c.profile && <div className="text-xs text-muted">{c.profile}</div>}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <Panel title="What each cluster moves and uses">
        <State loading={segments.loading} error={segments.error} />
        {segments.data && (
          <HeatGrid heatmap={segments.data} format={pct} rowLabel={(r) => r.replace("_", " ")} />
        )}
      </Panel>
    </div>
  );
}
