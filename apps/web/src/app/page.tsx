"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { AddressSearch } from "@/components/AddressSearch";
import { AddWalletForm } from "@/components/AddWalletForm";
import { HeatGrid } from "@/components/HeatGrid";
import { ChevronRight } from "@/components/icons";
import { AddressLink, Async, EmptyState, PageHeader, Panel, Skeleton, SkeletonRows } from "@/components/ui";
import type { Cluster, Heatmap, TraderPage, WatchPage } from "@/lib/api";
import { tagInfo } from "@/lib/copy";
import { num, pct, relativeTime, sentence, usd } from "@/lib/format";
import { type ApiState, useApi } from "@/lib/useApi";
import { useNow } from "@/lib/useNow";

function count<T>(state: ApiState<T>, pick: (d: T) => number): ReactNode {
  if (state.error) return <span className="text-muted">—</span>;
  if (state.data === undefined) return <Skeleton className="h-8 w-16" />;
  return num(pick(state.data));
}

function Stage({
  step,
  title,
  value,
  detail,
  href,
  cta,
}: {
  step: number;
  title: string;
  value: ReactNode;
  detail: ReactNode;
  href: string;
  cta: string;
}) {
  return (
    <li className="flex min-w-0 flex-col bg-surface px-5 pt-4 pb-5">
      <p className="flex items-center gap-2 text-sm font-medium">
        <span aria-hidden="true" className="num inline-flex h-5 w-5 items-center justify-center rounded-full bg-ink text-[0.6875rem] font-semibold text-surface">
          {step}
        </span>
        <span className="sr-only">Step {step}: </span>
        {title}
      </p>
      <p className="num mt-3 text-[2.25rem] leading-none font-semibold tracking-[-0.02em]">{value}</p>
      <p className="mt-2 min-h-10 text-[0.8125rem] leading-snug text-muted">{detail}</p>
      <Link href={href} className="mt-3 inline-flex min-h-8 items-center gap-1 self-start text-sm font-medium text-primary underline-offset-2 hover:underline">
        {cta}
        <ChevronRight size={14} />
      </Link>
    </li>
  );
}

export default function Overview() {
  const now = useNow();
  const everyone = useApi<TraderPage>("/v1/traders", { include_bots: true, limit: 1 });
  const top = useApi<TraderPage>("/v1/traders", { include_bots: false, sort: "volume", limit: 6 });
  const watch = useApi<WatchPage>("/v1/watchlist", { active: true, limit: 1 });
  const seeds = useApi<WatchPage>("/v1/watchlist", { origin: "seed", active: true, limit: 1 });
  const traders = useApi<WatchPage>("/v1/watchlist", { origin: "trader", active: true, limit: 1 });
  const neighbours = useApi<WatchPage>("/v1/watchlist", { origin: "neighbour", active: true, limit: 1 });
  const tags = useApi<Record<string, number>>("/v1/tags");
  const clusters = useApi<Cluster[]>("/v1/clusters");
  const segments = useApi<Heatmap>("/v1/heatmaps/segments", { by: "tag" });

  const humans = top.data?.total;
  const bots = everyone.data && humans !== undefined ? everyone.data.total - humans : undefined;
  const tagEntries = Object.entries(tags.data ?? {}).sort((a, b) => b[1] - a[1]);
  const maxTag = Math.max(1, ...tagEntries.map(([, n]) => n));

  return (
    <div className="space-y-8">
      <PageHeader
        title="From DEX trades to audiences"
        description="HeatMap reads swaps on Uniswap and SushiSwap, sets the bots aside, and follows the people behind the biggest trades. It then maps who they deal with and groups everyone by behaviour, ready to become audience segments."
      />

      <section aria-label="Pipeline">
        <ol className="grid gap-px overflow-hidden rounded-[10px] border border-line bg-line sm:grid-cols-2 xl:grid-cols-4">
          <Stage
            step={1}
            title="Discover"
            value={count(top, (d) => d.total)}
            detail={
              bots !== undefined
                ? `people trading on DEXs, after setting aside ${num(bots)} bots`
                : "people trading on DEXs, with bots set aside"
            }
            href="/discover"
            cta="Browse traders"
          />
          <Stage
            step={2}
            title="Track"
            value={count(watch, (d) => d.total)}
            detail={
              seeds.data && traders.data
                ? `wallets on the watchlist: ${num(seeds.data.total)} seeds, ${num(traders.data.total)} promoted traders`
                : "wallets on the watchlist"
            }
            href="/watchlist"
            cta="Open the watchlist"
          />
          <Stage
            step={3}
            title="Expand"
            value={count(neighbours, (d) => d.total)}
            detail="neighbours found around tracked wallets, by who they transfer with"
            href="/watchlist?origin=neighbour"
            cta="See neighbours"
          />
          <Stage
            step={4}
            title="Segment"
            value={count(clusters, (d) => d.filter((c) => c.cluster_id >= 0).length)}
            detail={tags.data ? `behaviour clusters, and ${num(Object.keys(tags.data).length)} tags in use` : "behaviour clusters"}
            href="/clusters"
            cta="Explore clusters"
          />
        </ol>
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Panel
            flush
            title="Biggest traders right now"
            description="People, not bots, ranked by DEX volume."
            action={
              <Link href="/discover" className="inline-flex min-h-8 items-center gap-1 text-sm font-medium text-primary underline-offset-2 hover:underline">
                All traders
                <ChevronRight size={14} />
              </Link>
            }
          >
            <Async
              state={top}
              skeleton={<SkeletonRows rows={6} className="px-5 pb-4" />}
              isEmpty={(d) => d.items.length === 0}
              empty={
                <div className="px-5 pb-4">
                  <EmptyState compact title="No traders discovered yet">
                    Traders appear after the discovery job has read recent DEX swaps.
                  </EmptyState>
                </div>
              }
            >
              {(d) => (
                <ol className="border-t border-line">
                  {d.items.map((t, i) => (
                    <li key={t.address} className="flex items-center gap-3 border-b border-line px-4 py-2.5 last:border-b-0 sm:px-5">
                      <span className="num w-5 text-right text-xs text-muted">{i + 1}</span>
                      <span className="min-w-0 flex-1">
                        <AddressLink address={t.address} />
                        <span className="block truncate text-xs text-muted">
                          {num(t.tx_count)} trades, mostly {t.top_tokens.slice(0, 2).map((x) => x.symbol ?? "unknown").join(" and ") || "various tokens"}
                        </span>
                      </span>
                      <span className="text-right">
                        <span className="num block text-sm font-medium">{usd(t.volume_usd)}</span>
                        <span className="block text-xs text-muted">{relativeTime(t.last_trade_at, now)}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </Async>
          </Panel>
        </div>
        <div className="space-y-6 lg:col-span-2">
          <Panel title="Open a wallet" description="Any Ethereum address, tracked or not.">
            <AddressSearch />
          </Panel>
          <Panel title="Track a wallet" description="Add a seed you already know about.">
            <AddWalletForm
              onAdded={() => {
                watch.reload();
                seeds.reload();
              }}
            />
          </Panel>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <Panel title="Behaviour tags" description="How many tracked wallets carry each tag.">
            <Async
              state={tags}
              skeleton={<SkeletonRows rows={5} />}
              isEmpty={(d) => Object.keys(d).length === 0}
              empty={
                <EmptyState compact title="No tags yet">
                  Tags are assigned by the models job once tracked wallets have behaviour snapshots.
                </EmptyState>
              }
            >
              {() => (
                <ul className="space-y-3">
                  {tagEntries.map(([tag, n]) => {
                    const info = tagInfo(tag);
                    return (
                      <li key={tag} title={info.summary || undefined}>
                        <div className="flex items-baseline justify-between gap-3 text-sm">
                          <span className={info.risk ? "font-medium text-danger" : "font-medium"}>
                            {info.title}
                            {info.risk && <span className="sr-only"> (risk signal)</span>}
                          </span>
                          <span className="num text-muted">{num(n)}</span>
                        </div>
                        <span aria-hidden="true" className="mt-1 block h-1.5 rounded-full bg-surface-2">
                          <span className={`block h-full rounded-full ${info.risk ? "bg-danger" : "bg-primary"}`} style={{ width: `${(n / maxTag) * 100}%` }} />
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Async>
          </Panel>
        </div>
        <div className="lg:col-span-3">
          <Panel
            title="What each tag moves and uses"
            description="Share of transfers by asset type and destination, per tag."
            action={
              <Link href="/clusters" className="inline-flex min-h-8 items-center gap-1 text-sm font-medium text-primary underline-offset-2 hover:underline">
                By cluster
                <ChevronRight size={14} />
              </Link>
            }
          >
            <Async
              state={segments}
              skeleton={<SkeletonRows rows={6} />}
              isEmpty={(h) => h.rows.length === 0}
              empty={
                <EmptyState compact title="No segment data yet">
                  This fills in once tracked wallets have tags.
                </EmptyState>
              }
            >
              {(h) => <HeatGrid heatmap={h} format={(v) => pct(v)} rowLabel={(r) => tagInfo(r).title || sentence(r)} />}
            </Async>
          </Panel>
        </div>
      </div>
    </div>
  );
}
