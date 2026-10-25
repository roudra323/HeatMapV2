"use client";

import Link from "next/link";
import { useState } from "react";

import { HeatGrid } from "@/components/HeatGrid";
import { AlertIcon, ChevronRight, ExternalIcon, NetworkIcon } from "@/components/icons";
import { NeighbourGraph } from "@/components/NeighbourGraph";
import { OriginBadge } from "@/components/OriginBadge";
import { TimelineChart } from "@/components/TimelineChart";
import { TrackButton } from "@/components/TrackButton";
import { TradesPanel } from "@/components/TradesTable";
import {
  AddressLink,
  Async,
  Badge,
  CopyButton,
  EmptyState,
  ErrorState,
  Panel,
  Segmented,
  Skeleton,
  SkeletonRows,
  StatStrip,
} from "@/components/ui";
import type {
  Heatmap,
  Label,
  Network,
  SimilarWallet,
  TimelineBucket,
  TransferPage,
  WalletProfile,
  WatchEntry,
} from "@/lib/api";
import { originOf, tagInfo } from "@/lib/copy";
import { date, dateTime, num, pct, relativeTime, sentence, shortAddress, usd } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useExplorer } from "@/lib/useExplorer";
import { useNow } from "@/lib/useNow";

const WINDOWS = ["7d", "30d", "90d", "all"] as const;
type Window = (typeof WINDOWS)[number];

export function WalletView({ address }: { address: string }) {
  const [featureWindow, setFeatureWindow] = useState<Window>("all");
  const base = `/v1/wallets/${address}`;
  const profile = useApi<WalletProfile>(base, { window: featureWindow });
  const explorer = useExplorer();

  const notSeen = profile.status === 404;
  const p = profile.data;
  const tracked = Boolean(p?.watch?.active);

  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb">
        <ol className="flex items-center gap-1 text-[0.8125rem] text-muted">
          <li>
            <Link href={tracked ? "/watchlist" : "/discover"} className="hover:text-ink">
              {tracked ? "Watchlist" : "Discover"}
            </Link>
          </li>
          <li aria-hidden="true">
            <ChevronRight size={14} />
          </li>
          <li aria-current="page" className="mono text-ink">
            {shortAddress(address)}
          </li>
        </ol>
      </nav>

      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div className="min-w-0 space-y-2">
          <h1 className="text-[1.625rem] leading-tight font-semibold tracking-[-0.015em] sm:text-[1.875rem]">
            {p?.entity?.name ?? "Wallet"}
            {p?.entity && <span className="ml-2 align-middle text-base font-normal text-muted">{sentence(p.entity.category)}</span>}
          </h1>
          <div className="flex flex-wrap items-center gap-1">
            <span className="mono text-sm break-all text-ink">{address}</span>
            <CopyButton text={address} />
            {explorer && (
              <a
                href={`${explorer}/address/${address}`}
                target="_blank"
                rel="noreferrer"
                aria-label="View on the block explorer (opens in a new tab)"
                title="View on the block explorer"
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"
              >
                <ExternalIcon />
              </a>
            )}
          </div>
          {profile.loading && !p && !profile.error ? <Skeleton className="h-6 w-72" /> : <WatchLine profile={p} notSeen={notSeen} />}
        </div>
        {(notSeen || (p && !tracked)) && (
          <TrackButton address={address} tracked={false} size="md" variant="primary" onTracked={profile.reload} />
        )}
      </header>

      {profile.error && !notSeen && <ErrorState message={profile.error} onRetry={profile.reload} />}

      {notSeen && (
        <div className="flex gap-3 rounded-[10px] border border-line bg-surface px-4 py-4 sm:px-5">
          <AlertIcon className="mt-0.5 shrink-0 text-muted" />
          <div className="text-sm leading-relaxed">
            <p className="font-medium">Not on the watchlist yet</p>
            <p className="mt-0.5 max-w-prose text-muted">
              HeatMap only builds a full profile for wallets it tracks. Track this wallet to sync its transfer history, map its
              neighbours and compute its behaviour, tags and cluster. Its DEX trades are shown below already.
            </p>
          </div>
        </div>
      )}

      {p && <ProfilePanel profile={p} window={featureWindow} onWindow={setFeatureWindow} reloading={profile.loading} />}

      <TradesPanel address={address} />

      <ActivityPanels address={address} />

      <NeighboursPanel address={address} />

      <div className="grid gap-6 lg:grid-cols-3">
        <SimilarPanel address={address} profile={p} />
        <div className="lg:col-span-2">
          <TransfersPanel address={address} />
        </div>
      </div>

      {p && (
        <p className="text-xs leading-relaxed text-muted">
          Behaviour snapshot {dateTime(p.snapshot_at)}. Synced to block {p.watch?.last_block?.toLocaleString("en-US") ?? "not yet"}.
          Last seen on chain {date(p.last_seen_at)}.
        </p>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- how it got here */

function WatchLine({ profile, notSeen }: { profile: WalletProfile | undefined; notSeen: boolean }) {
  if (notSeen || !profile) return notSeen ? <Badge>Not tracked</Badge> : null;
  const w = profile.watch;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted">
      {w ? <OriginBadge entry={w} /> : <Badge>Not tracked</Badge>}
      {w && <OriginDetail entry={w} />}
      {w?.note && <span className="basis-full text-ink">{w.note}</span>}
      {w && !w.active && <Badge tone="danger">Untracked</Badge>}
      {profile.funded_by && (
        <span>
          First funded by <AddressLink address={profile.funded_by} />
        </span>
      )}
      {profile.community_id !== null && <span>Community #{profile.community_id}</span>}
    </div>
  );
}

function OriginDetail({ entry }: { entry: WatchEntry }) {
  if (entry.origin === "neighbour") {
    return (
      <span>
        Found {entry.hop === 1 ? "1 hop" : `${entry.hop} hops`} out
        {entry.via_address && (
          <>
            {" "}from <AddressLink address={entry.via_address} />
          </>
        )}
        , tracked since {date(entry.created_at)}
      </span>
    );
  }
  return (
    <span>
      {originOf(entry.origin).summary} Tracked since {date(entry.created_at)}.
    </span>
  );
}

/* --------------------------------------------------------------- behaviour */

function LabelRow({ label, title, risky }: { label: Label; title: string; risky?: boolean }) {
  return (
    <li className="flex gap-3 py-2.5">
      <span aria-hidden="true" className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${risky ? "bg-danger" : "bg-primary"}`} />
      <div className="min-w-0 text-sm">
        <p className="font-medium">
          {title}
          {risky && <span className="sr-only"> (risk signal)</span>}
          {label.score !== null && (
            <span className="num ml-2 text-xs font-normal text-muted" title="Strength of the evidence, 0 to 1">
              strength {label.score.toFixed(2)}
            </span>
          )}
        </p>
        {label.reason && <p className="mt-0.5 leading-relaxed text-muted">{label.reason}</p>}
      </div>
    </li>
  );
}

function ProfilePanel({
  profile: p,
  window,
  onWindow,
  reloading,
}: {
  profile: WalletProfile;
  window: Window;
  onWindow: (w: Window) => void;
  reloading: boolean;
}) {
  const s = p.summary as Record<string, unknown>;
  const hasSnapshot = Boolean(p.snapshot_at);
  const findings: { key: string; label: Label; title: string; risky?: boolean }[] = [
    ...p.tags.map((t) => ({ key: `tag-${t.label}`, label: t, title: tagInfo(t.label).title, risky: tagInfo(t.label).risk })),
    ...(p.cluster ? [{ key: "cluster", label: p.cluster, title: `In ${sentence(p.cluster.label).toLowerCase()}` }] : []),
    ...(p.anomaly?.label === "outlier" ? [{ key: "anomaly", label: p.anomaly, title: "Unusual behaviour (outlier)", risky: true }] : []),
    ...(p.drift?.label === "behaviour_changed"
      ? [{ key: "drift", label: p.drift, title: "Behaviour changed recently", risky: true }]
      : []),
  ];

  return (
    <Panel
      title="Behaviour profile"
      description="Measured from this wallet's transfers over the selected window."
      action={
        <Segmented
          label="Time window"
          value={window}
          onChange={onWindow}
          options={WINDOWS.map((w) => ({ value: w, label: w === "all" ? "All time" : w }))}
        />
      }
    >
      <div aria-busy={reloading} className={`space-y-5 transition-opacity duration-150 ${reloading ? "opacity-60" : ""}`}>
        {hasSnapshot ? (
          <>
            <StatStrip
              items={[
                { label: "Transfers", value: num(s.transfer_count) },
                { label: "Volume", value: usd(s.volume_usd) },
                { label: "Net flow", value: usd(s.netflow_usd), hint: "Received minus sent" },
                { label: "Counterparties", value: num(s.degree) },
                { label: "Stablecoin share", value: pct(s.share_stablecoin) },
                { label: "Days since last", value: num(s.days_since_last, 1) },
              ]}
            />
            <div>
              <h3 className="text-sm font-semibold">What stands out</h3>
              {findings.length > 0 ? (
                <ul className="mt-1 divide-y divide-line">
                  {findings.map((f) => (
                    <LabelRow key={f.key} label={f.label} title={f.title} risky={f.risky} />
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-muted">
                  No tags, cluster or anomalies for this window yet. They are assigned when the models job runs.
                </p>
              )}
            </div>
          </>
        ) : (
          <EmptyState title={`No behaviour snapshot for ${window === "all" ? "all time" : `the last ${window}`} yet`} compact>
            Features are computed after the wallet&apos;s history has synced. Try another window, or check back after the next
            pipeline run.
          </EmptyState>
        )}
      </div>
    </Panel>
  );
}

/* --------------------------------------------------------------- activity */

function ActivityPanels({ address }: { address: string }) {
  const base = `/v1/wallets/${address}`;
  const heatmap = useApi<Heatmap>(`${base}/heatmap`, { days: 365 });
  const timeline = useApi<TimelineBucket[]>(`${base}/timeline`, { bucket: "week", days: 365 });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title="When it's active" description="Transfers by weekday and hour, UTC, last 365 days.">
        <Async
          state={heatmap}
          skeleton={<Skeleton className="h-44 w-full" />}
          isEmpty={(h) => h.values.every((row) => row.every((v) => !v))}
          empty={<EmptyState compact title="No transfers in the last year">Activity appears once the wallet&apos;s history has synced.</EmptyState>}
        >
          {(h) => <HeatGrid heatmap={h} columnLabel={(c) => c} format={(v) => `${v} transfers`} compact />}
        </Async>
      </Panel>
      <Panel title="Weekly activity" description="Transfers in and out per week, last 365 days.">
        <Async
          state={timeline}
          skeleton={<Skeleton className="h-44 w-full" />}
          isEmpty={(t) => t.length === 0}
          empty={<EmptyState compact title="No activity in range">Activity appears once the wallet&apos;s history has synced.</EmptyState>}
        >
          {(t) => <TimelineChart buckets={t} />}
        </Async>
      </Panel>
    </div>
  );
}

function NeighboursPanel({ address }: { address: string }) {
  const [depth, setDepth] = useState(1);
  const network = useApi<Network>(`/v1/wallets/${address}/neighbors`, { depth, limit: 30 });
  return (
    <Panel
      title="Neighbours"
      description="Wallets it transfers with most. Thicker lines mean more transfers. Select a wallet to open it."
      action={
        <Segmented
          label="Network depth"
          value={depth}
          onChange={setDepth}
          options={[
            { value: 1, label: "1 hop" },
            { value: 2, label: "2 hops" },
          ]}
        />
      }
    >
      <Async
        state={network}
        skeleton={<Skeleton className="h-72 w-full" />}
        isEmpty={(n) => n.nodes.length <= 1}
        empty={
          <EmptyState compact icon={<NetworkIcon size={20} />} title="No neighbours mapped yet">
            Neighbours are found after the wallet is tracked and its transfers have synced.
          </EmptyState>
        }
      >
        {(n) => <NeighbourGraph network={n} />}
      </Async>
    </Panel>
  );
}

function SimilarPanel({ address, profile }: { address: string; profile: WalletProfile | undefined }) {
  const similar = useApi<SimilarWallet[]>(`/v1/wallets/${address}/similar`, { limit: 8 });
  const s = (profile?.summary ?? {}) as Record<string, unknown>;
  return (
    <Panel title="Behaves most like" description="Wallets with the closest behaviour profile.">
      <Async
        state={similar}
        skeleton={<SkeletonRows rows={4} />}
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState compact title="No comparable wallets yet">
            Similar wallets appear once this wallet has a behaviour snapshot.
          </EmptyState>
        }
      >
        {(d) => (
          <ul className="divide-y divide-line">
            {d.map((w) => (
              <li key={w.address} className="flex items-center justify-between gap-3 py-2">
                <AddressLink address={w.address} />
                <span className="flex w-24 items-center gap-2">
                  <span aria-hidden="true" className="block h-1.5 flex-1 rounded-full bg-surface-2">
                    <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.max(0, w.similarity) * 100}%` }} />
                  </span>
                  <span className="num text-xs text-muted" aria-label={`similarity ${w.similarity.toFixed(2)}`}>
                    {w.similarity.toFixed(2)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Async>
      {typeof s.most_similar_wallet === "string" && (
        <p className="mt-3 text-xs leading-relaxed text-muted">
          Shares the most counterparties with <AddressLink address={s.most_similar_wallet} /> ({pct(s.max_counterparty_jaccard)} overlap).
        </p>
      )}
    </Panel>
  );
}

function TransfersPanel({ address }: { address: string }) {
  const transfers = useApi<TransferPage>(`/v1/wallets/${address}/transfers`, { limit: 15 });
  const now = useNow();
  return (
    <Panel
      flush
      title={
        <span className="flex items-center gap-2">
          Recent transfers
          {transfers.data && transfers.data.total > 0 && (
            <span className="num text-sm font-normal text-muted">{num(transfers.data.total)}</span>
          )}
        </span>
      }
      description="Token and ETH movements, spam excluded."
    >
      <Async
        state={transfers}
        skeleton={<SkeletonRows rows={6} className="px-5 pb-4" />}
        isEmpty={(d) => d.items.length === 0}
        empty={
          <div className="px-4 pb-4 sm:px-5">
            <EmptyState compact title="No transfers synced yet">
              Transfers appear once the wallet is tracked and its history has synced.
            </EmptyState>
          </div>
        }
      >
        {(d) => (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-sm">
              <thead>
                <tr className="border-y border-line text-left text-xs text-muted">
                  <th scope="col" className="py-2.5 pr-3 pl-5 font-medium">When</th>
                  <th scope="col" className="py-2.5 pr-3 font-medium">Direction</th>
                  <th scope="col" className="py-2.5 pr-3 font-medium">Counterparty</th>
                  <th scope="col" className="py-2.5 pr-3 font-medium">Type</th>
                  <th scope="col" className="py-2.5 pr-5 text-right font-medium">Value</th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((t) => {
                  const out = t.from_address === address;
                  const cp = out ? t.to_address : t.from_address;
                  return (
                    <tr
                      key={`${t.tx_hash}-${t.from_address}-${t.to_address}-${t.token_address}-${t.token_id}`}
                      className="border-b border-line last:border-b-0 hover:bg-surface-2"
                    >
                      <td className="py-2.5 pr-3 pl-5 whitespace-nowrap text-muted" title={dateTime(t.block_time)}>
                        {relativeTime(t.block_time, now)}
                      </td>
                      <td className="py-2.5 pr-3">{out ? <Badge>Sent</Badge> : <Badge tone="ok">Received</Badge>}</td>
                      <td className="py-2.5 pr-3">
                        <AddressLink address={cp} />
                      </td>
                      <td className="py-2.5 pr-3 text-muted">{sentence(t.category)}</td>
                      <td className="num py-2.5 pr-5 text-right">{usd(t.amount_usd)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Async>
    </Panel>
  );
}

