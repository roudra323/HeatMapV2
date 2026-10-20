"use client";

import { useState } from "react";

import { HeatGrid } from "@/components/HeatGrid";
import { NeighbourGraph } from "@/components/NeighbourGraph";
import { TimelineChart } from "@/components/TimelineChart";
import { AddressLink, Chip, Panel, Stat, State } from "@/components/ui";
import {
  api,
  type Heatmap,
  type Label,
  type Network,
  type SimilarWallet,
  type TimelineBucket,
  type TransferPage,
  type WalletProfile,
} from "@/lib/api";
import { date, num, pct, shortAddress, usd } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const WINDOWS = ["7d", "30d", "90d", "all"] as const;

function LabelChip({ label }: { label: Label }) {
  const risky = ["sybil_suspect", "mixer_exposure", "bot_like"].includes(label.label);
  return (
    <Chip tone={risky ? "danger" : "accent"} title={label.reason ?? undefined}>
      {label.label.replaceAll("_", " ")}
      {label.score !== null && <span className="ml-1 opacity-60">{label.score.toFixed(2)}</span>}
    </Chip>
  );
}

export function WalletView({ address }: { address: string }) {
  const [featureWindow, setFeatureWindow] = useState<(typeof WINDOWS)[number]>("all");
  const [depth, setDepth] = useState(1);
  const base = `/v1/wallets/${address}`;
  const profile = useApi<WalletProfile>(base, { window: featureWindow });
  const heatmap = useApi<Heatmap>(`${base}/heatmap`, { days: 365 });
  const timeline = useApi<TimelineBucket[]>(`${base}/timeline`, { bucket: "week", days: 365 });
  const network = useApi<Network>(`${base}/neighbors`, { depth, limit: 30 });
  const similar = useApi<SimilarWallet[]>(`${base}/similar`, { limit: 8 });
  const transfers = useApi<TransferPage>(`${base}/transfers`, { limit: 15 });

  if (profile.loading && !profile.data) return <State loading />;
  if (profile.error || !profile.data) {
    return (
      <Panel title={shortAddress(address)}>
        <State error={profile.error ?? "Not found"} />
        <button
          onClick={() => api.post("/v1/watchlist", { address }).then(profile.reload)}
          className="mt-3 rounded-md bg-accent px-3 py-1.5 text-sm text-white"
        >
          Track this wallet
        </button>
      </Panel>
    );
  }

  const p = profile.data;
  const s = p.summary as Record<string, unknown>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="mono break-all text-lg">{p.address}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            {p.entity && <Chip>{`${p.entity.name} · ${p.entity.category}`}</Chip>}
            {p.kind && <span>{p.kind}</span>}
            {p.watch ? (
              <span>
                {p.watch.origin === "seed" ? "seed" : `neighbour (hop ${p.watch.hop}`}
                {p.watch.via_address && (
                  <>
                    {" via "}
                    <AddressLink address={p.watch.via_address} />)
                  </>
                )}
              </span>
            ) : (
              <span>not tracked</span>
            )}
            {p.funded_by && (
              <span>
                funded by <AddressLink address={p.funded_by} />
              </span>
            )}
            {p.community_id !== null && <span>community #{p.community_id}</span>}
          </div>
        </div>
        <div className="flex gap-1 rounded-md border border-line p-0.5 text-xs">
          {WINDOWS.map((w) => (
            <button
              key={w}
              onClick={() => setFeatureWindow(w)}
              className={`rounded px-2 py-1 ${w === featureWindow ? "bg-accent text-white" : "text-muted"}`}
            >
              {w}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {p.tags.map((t) => (
          <LabelChip key={t.label} label={t} />
        ))}
        {p.cluster && (
          <Chip title={p.cluster.reason ?? undefined}>{p.cluster.label.replace("_", " ")}</Chip>
        )}
        {p.anomaly?.label === "outlier" && (
          <Chip tone="danger" title={p.anomaly.reason ?? undefined}>
            outlier
          </Chip>
        )}
        {p.drift?.label === "behaviour_changed" && (
          <Chip tone="danger" title={p.drift.reason ?? undefined}>
            behaviour changed
          </Chip>
        )}
        {!p.snapshot_at && <span className="text-sm text-muted">No feature snapshot for {featureWindow} yet.</span>}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        <Stat label="Transfers" value={num(s.transfer_count)} />
        <Stat label="Volume" value={usd(s.volume_usd as number)} />
        <Stat label="Net flow" value={usd(s.netflow_usd as number)} />
        <Stat label="Counterparties" value={num(s.degree)} />
        <Stat label="Stablecoin share" value={pct(s.share_stablecoin)} />
        <Stat label="Days since last" value={num(s.days_since_last, 1)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Activity by weekday and hour (UTC, last 365 days)">
          <State loading={heatmap.loading} error={heatmap.error} />
          {heatmap.data && (
            <HeatGrid heatmap={heatmap.data} columnLabel={(c) => c} format={(v) => `${v} transfers`} />
          )}
        </Panel>
        <Panel title="Weekly activity">
          <State loading={timeline.loading} error={timeline.error} />
          {timeline.data && <TimelineChart buckets={timeline.data} />}
        </Panel>
      </div>

      <Panel
        title="Neighbours"
        action={
          <select
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="rounded-md border border-line bg-bg px-2 py-1 text-xs"
          >
            <option value={1}>1 hop</option>
            <option value={2}>2 hops</option>
          </select>
        }
      >
        <State loading={network.loading} error={network.error} />
        {network.data && <NeighbourGraph network={network.data} />}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Behaves most like">
          <State
            loading={similar.loading}
            error={similar.error}
            empty={similar.data?.length === 0 ? "No comparable wallets yet." : undefined}
          />
          <ul className="space-y-1.5 text-sm">
            {similar.data?.map((w) => (
              <li key={w.address} className="flex items-center justify-between gap-2">
                <AddressLink address={w.address} />
                <span className="mono text-xs text-muted">{w.similarity.toFixed(2)}</span>
              </li>
            ))}
          </ul>
          {s.most_similar_wallet ? (
            <p className="mt-3 text-xs text-muted">
              Most shared counterparties: <AddressLink address={String(s.most_similar_wallet)} />{" "}
              ({pct(s.max_counterparty_jaccard)})
            </p>
          ) : null}
        </Panel>
        <div className="lg:col-span-2">
          <Panel title={`Recent transfers${transfers.data ? ` (${transfers.data.total})` : ""}`}>
            <State loading={transfers.loading} error={transfers.error} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted">
                  <tr>
                    <th className="py-1">Date</th>
                    <th>Direction</th>
                    <th>Counterparty</th>
                    <th>Type</th>
                    <th className="text-right">USD</th>
                  </tr>
                </thead>
                <tbody>
                  {transfers.data?.items.map((t) => {
                    const out = t.from_address === address;
                    const cp = out ? t.to_address : t.from_address;
                    return (
                      <tr key={`${t.tx_hash}-${t.from_address}-${t.to_address}-${t.token_address}-${t.token_id}`} className="border-t border-line">
                        <td className="py-1.5">{date(t.block_time)}</td>
                        <td className={out ? "text-accent" : "text-ok"}>{out ? "out" : "in"}</td>
                        <td>
                          <AddressLink address={cp} />
                        </td>
                        <td className="text-muted">{t.category}</td>
                        <td className="mono text-right">{usd(t.amount_usd)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </div>

      <p className="text-xs text-muted">
        Snapshot {date(p.snapshot_at)} · sync to block {p.watch?.last_block ?? "—"} · last seen{" "}
        {date(p.last_seen_at)}
      </p>
    </div>
  );
}
