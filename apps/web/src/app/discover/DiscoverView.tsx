"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Fragment, useState } from "react";

import { ArrowDown, ChevronDown, CompassIcon, InfoIcon } from "@/components/icons";
import { TrackButton } from "@/components/TrackButton";
import { BotBadge, TraderVerdict } from "@/components/TraderVerdict";
import {
  AddressLink,
  Async,
  Badge,
  buttonClass,
  EmptyState,
  PageHeader,
  Pagination,
  Panel,
  SelectField,
  SkeletonRows,
  StatStrip,
  Switch,
} from "@/components/ui";
import type { Trader, TraderPage } from "@/lib/api";
import { BOT_REASONS, protocolName, PROTOCOLS } from "@/lib/copy";
import { dateTime, num, pct, relativeTime, toNumber, usd, usdCompact } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useNow } from "@/lib/useNow";

const PAGE = 50;
/** The API's largest page; the summary strip sums volume over at most this many traders. */
const SAMPLE = 500;

type Sort = "volume" | "tx_count" | "last_trade";

const SORTS: { value: Sort; label: string }[] = [
  { value: "volume", label: "Volume" },
  { value: "tx_count", label: "Number of trades" },
  { value: "last_trade", label: "Most recent trade" },
];

const MIN_VOLUMES = [
  { value: "", label: "Any volume" },
  { value: "1000", label: "$1K or more" },
  { value: "10000", label: "$10K or more" },
  { value: "50000", label: "$50K or more" },
  { value: "100000", label: "$100K or more" },
  { value: "1000000", label: "$1M or more" },
];

const PROTOCOL_OPTIONS = [
  { value: "", label: "All DEXs" },
  ...Object.entries(PROTOCOLS).map(([value, p]) => ({ value, label: p.name })),
];

function useFilters() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const sortParam = params.get("sort");
  const filters = {
    bots: params.get("bots") === "1",
    protocol: params.get("protocol") ?? "",
    min: params.get("min") ?? "",
    sort: (SORTS.some((s) => s.value === sortParam) ? sortParam : "volume") as Sort,
    offset: Math.max(0, Number(params.get("offset")) || 0),
  };
  function update(next: Partial<typeof filters>) {
    const merged = { ...filters, offset: 0, ...next };
    const q = new URLSearchParams();
    if (merged.bots) q.set("bots", "1");
    if (merged.protocol) q.set("protocol", merged.protocol);
    if (merged.min) q.set("min", merged.min);
    if (merged.sort !== "volume") q.set("sort", merged.sort);
    if (merged.offset) q.set("offset", String(merged.offset));
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }
  return { filters, update };
}

export function DiscoverView() {
  const { filters, update } = useFilters();
  const now = useNow();
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [justTracked, setJustTracked] = useState<Set<string>>(new Set());

  const common = {
    min_volume_usd: filters.min || undefined,
    protocol: filters.protocol || undefined,
  };
  const list = useApi<TraderPage>("/v1/traders", {
    ...common,
    include_bots: filters.bots,
    sort: filters.sort,
    limit: PAGE,
    offset: filters.offset,
  });
  const humans = useApi<TraderPage>("/v1/traders", { ...common, include_bots: false, sort: "volume", limit: SAMPLE });
  const everyone = useApi<TraderPage>("/v1/traders", { ...common, include_bots: true, limit: 1 });

  const humanTotal = humans.data?.total;
  const botTotal = everyone.data && humanTotal !== undefined ? everyone.data.total - humanTotal : undefined;
  const volume = humans.data?.items.reduce((sum, t) => sum + (toNumber(t.volume_usd) ?? 0), 0);
  const partial = humans.data ? humans.data.total > humans.data.items.length : false;
  const trackedCount = humans.data?.items.filter((t) => t.tracked || justTracked.has(t.address)).length;
  const maxVolume = Math.max(
    1,
    toNumber(humans.data?.items[0]?.volume_usd) ?? 0,
    ...(list.data?.items.map((t) => toNumber(t.volume_usd) ?? 0) ?? []),
  );
  const updatedAt = list.data?.items[0]?.computed_at ?? humans.data?.items[0]?.computed_at;

  function toggle(address: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(address)) next.delete(address);
      else next.add(address);
      return next;
    });
  }
  function markTracked(address: string) {
    setJustTracked((prev) => new Set(prev).add(address));
  }
  const isTracked = (t: Trader) => t.tracked || justTracked.has(t.address);
  const filtered = Boolean(filters.min || filters.protocol);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Discover traders"
        description="Wallets that signed swaps on Uniswap and SushiSwap recently, biggest first. Bots are filtered out so what remains are people you can track and segment."
        actions={
          updatedAt ? (
            <p className="text-[0.8125rem] text-muted" title={dateTime(updatedAt)}>
              Scores updated {relativeTime(updatedAt, now)}
            </p>
          ) : undefined
        }
      />

      <StatStrip
        items={[
          {
            label: "People trading",
            value: humanTotal !== undefined ? num(humanTotal) : "—",
            loading: humans.data === undefined && !humans.error,
            hint: filtered ? "Matching your filters" : "Human traders in the discovery window",
          },
          {
            label: "Bots filtered out",
            value: botTotal !== undefined ? num(botTotal) : "—",
            loading: (everyone.data === undefined || humans.data === undefined) && !everyone.error && !humans.error,
            hint:
              botTotal !== undefined && everyone.data && everyone.data.total > 0
                ? `${pct(botTotal / everyone.data.total)} of all signers`
                : undefined,
          },
          {
            label: partial ? `Volume, top ${SAMPLE} people` : "Volume traded by people",
            value: volume !== undefined ? usdCompact(volume) : "—",
            loading: humans.data === undefined && !humans.error,
            hint: partial ? "Summed over the largest traders only" : undefined,
          },
          {
            label: "Already on the watchlist",
            value: trackedCount !== undefined ? num(trackedCount) : "—",
            loading: humans.data === undefined && !humans.error,
            hint:
              humans.data && humans.data.items.length > 0
                ? partial
                  ? `among the top ${num(humans.data.items.length)} people`
                  : `of ${num(humans.data.items.length)} people`
                : undefined,
          },
        ]}
      />

      <Panel flush>
        <div className="flex flex-wrap items-end gap-x-4 gap-y-3 border-b border-line px-4 pt-4 pb-4 sm:px-5">
          <div className="w-full sm:w-44">
            <SelectField label="DEX" value={filters.protocol} options={PROTOCOL_OPTIONS} onChange={(protocol) => update({ protocol })} />
          </div>
          <div className="w-full sm:w-44">
            <SelectField label="Volume" value={filters.min} options={MIN_VOLUMES} onChange={(min) => update({ min })} />
          </div>
          <div className="w-full sm:w-48">
            <SelectField label="Sort by" value={filters.sort} options={SORTS} onChange={(sort) => update({ sort })} />
          </div>
          <div className="pb-2 sm:ml-auto">
            <Switch
              checked={filters.bots}
              onChange={(bots) => update({ bots })}
              label="Show bots"
              description={botTotal ? `${num(botTotal)} hidden` : undefined}
            />
          </div>
        </div>

        <Async
          state={list}
          skeleton={<SkeletonRows rows={10} className="p-5" />}
          isEmpty={(d) => d.items.length === 0}
          empty={
            <div className="p-5">
              <EmptyState
                icon={<CompassIcon size={20} />}
                title={filtered ? "No traders match these filters" : "No traders discovered yet"}
                action={
                  filtered ? (
                    <button type="button" className={buttonClass("secondary", "sm")} onClick={() => update({ protocol: "", min: "" })}>
                      Clear filters
                    </button>
                  ) : undefined
                }
              >
                {filtered
                  ? "Try a lower volume threshold or a different DEX."
                  : "Traders appear here after the discovery job has read recent DEX swaps."}
              </EmptyState>
            </div>
          }
        >
          {(page) => (
            <>
              {/* Desktop: one dense table. */}
              <div className="hidden lg:block">
                <table className="w-full text-sm">
                  <caption className="sr-only">
                    Traders sorted by {SORTS.find((s) => s.value === filters.sort)?.label.toLowerCase()}
                  </caption>
                  <thead>
                    <tr className="border-b border-line text-left text-xs text-muted">
                      <th scope="col" className="w-11 py-2.5 pl-3">
                        <span className="sr-only">Details</span>
                      </th>
                      <th scope="col" className="py-2.5 font-medium">Trader</th>
                      <SortHeader label="Volume" sort="volume" current={filters.sort} onSort={(sort) => update({ sort })} />
                      <SortHeader label="Trades" sort="tx_count" current={filters.sort} onSort={(sort) => update({ sort })} align="right" />
                      <th scope="col" className="py-2.5 pr-3 text-right font-medium whitespace-nowrap">Active days</th>
                      <th scope="col" className="hidden py-2.5 pr-3 text-right font-medium xl:table-cell">Largest trade</th>
                      <th scope="col" className="py-2.5 pr-3 font-medium">DEXs</th>
                      <th scope="col" className="py-2.5 pr-3 font-medium">Top tokens</th>
                      <SortHeader label="Last trade" sort="last_trade" current={filters.sort} onSort={(sort) => update({ sort })} />
                      <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                        <span className="sr-only">Action</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((t) => {
                      const expanded = open.has(t.address);
                      const detailId = `trader-${t.address}`;
                      return (
                        <Fragment key={t.address}>
                          <tr className={`border-b border-line align-middle hover:bg-surface-2 ${t.is_bot ? "bg-surface-2/60" : ""}`}>
                            <td className="py-2.5 pl-3">
                              <button
                                type="button"
                                onClick={() => toggle(t.address)}
                                aria-expanded={expanded}
                                aria-controls={detailId}
                                aria-label={`${expanded ? "Hide" : "Show"} why ${t.address} is ${t.is_bot ? "a bot" : "counted as a person"}`}
                                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface hover:text-ink"
                              >
                                <ChevronDown className={`transition-transform duration-150 ${expanded ? "rotate-180" : ""}`} />
                              </button>
                            </td>
                            <td className="py-2.5 pr-3">
                              <div className="flex flex-col items-start gap-1">
                                <AddressLink address={t.address} />
                                {t.is_bot && <BotBadge reason={t.bot_reason} />}
                              </div>
                            </td>
                            <td className="py-2.5 pr-4">
                              <VolumeCell value={t.volume_usd} max={maxVolume} muted={t.is_bot} />
                            </td>
                            <td className="num py-2.5 pr-3 text-right">{num(t.tx_count)}</td>
                            <td className="num py-2.5 pr-3 text-right">{num(t.active_days)}</td>
                            <td className="num hidden py-2.5 pr-3 text-right xl:table-cell">{usd(t.max_tx_usd)}</td>
                            <td className="py-2.5 pr-3">
                              <ProtocolList protocols={t.protocols} />
                            </td>
                            <td className="py-2.5 pr-3">
                              <TokenList tokens={t.top_tokens} />
                            </td>
                            <td className="py-2.5 pr-3 whitespace-nowrap text-muted" title={dateTime(t.last_trade_at)}>
                              {relativeTime(t.last_trade_at, now)}
                            </td>
                            <td className="py-2.5 pr-4 text-right">
                              {!t.is_bot && (
                                <TrackButton address={t.address} tracked={isTracked(t)} onTracked={() => markTracked(t.address)} />
                              )}
                            </td>
                          </tr>
                          {expanded && (
                            <tr id={detailId} className="border-b border-line bg-surface-2/70">
                              <td />
                              <td colSpan={9} className="py-5 pr-6">
                                <TraderVerdict trader={t} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Phones and tablets: one card per trader. */}
              <ul className="divide-y divide-line lg:hidden">
                {page.items.map((t) => {
                  const expanded = open.has(t.address);
                  const detailId = `trader-m-${t.address}`;
                  return (
                    <li key={t.address} className={`px-4 py-4 sm:px-5 ${t.is_bot ? "bg-surface-2/60" : ""}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 flex-col items-start gap-1">
                          <AddressLink address={t.address} />
                          {t.is_bot && <BotBadge reason={t.bot_reason} />}
                        </div>
                        {!t.is_bot && <TrackButton address={t.address} tracked={isTracked(t)} onTracked={() => markTracked(t.address)} />}
                      </div>
                      <div className="mt-3">
                        <VolumeCell value={t.volume_usd} max={maxVolume} muted={t.is_bot} />
                      </div>
                      <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
                        <div>
                          <dt className="text-xs text-muted">Trades</dt>
                          <dd className="num">{num(t.tx_count)}</dd>
                        </div>
                        <div>
                          <dt className="text-xs text-muted">Active days</dt>
                          <dd className="num">{num(t.active_days)}</dd>
                        </div>
                        <div>
                          <dt className="text-xs text-muted">Last trade</dt>
                          <dd title={dateTime(t.last_trade_at)}>{relativeTime(t.last_trade_at, now)}</dd>
                        </div>
                      </dl>
                      <div className="mt-3 space-y-1.5 text-sm">
                        <TokenList tokens={t.top_tokens} />
                        <ProtocolList protocols={t.protocols} />
                      </div>
                      <button
                        type="button"
                        onClick={() => toggle(t.address)}
                        aria-expanded={expanded}
                        aria-controls={detailId}
                        className="mt-3 inline-flex min-h-9 items-center gap-1 text-[0.8125rem] font-medium text-primary"
                      >
                        {t.is_bot ? "Why it's a bot" : "Why it counts as a person"}
                        <ChevronDown size={14} className={`transition-transform duration-150 ${expanded ? "rotate-180" : ""}`} />
                      </button>
                      {expanded && (
                        <div id={detailId} className="mt-3 rounded-lg border border-line bg-surface p-4">
                          <TraderVerdict trader={t} />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>

              <div className="border-t border-line">
                <Pagination
                  offset={filters.offset}
                  limit={PAGE}
                  total={page.total}
                  noun={filters.bots ? "signers" : "traders"}
                  onChange={(offset) => {
                    update({ offset });
                    document.getElementById("main")?.scrollIntoView({ block: "start" });
                  }}
                />
              </div>
            </>
          )}
        </Async>
      </Panel>

      <BotGuide />
    </div>
  );
}

function SortHeader({
  label,
  sort,
  current,
  onSort,
  align = "left",
}: {
  label: string;
  sort: Sort;
  current: Sort;
  onSort: (sort: Sort) => void;
  align?: "left" | "right";
}) {
  const active = sort === current;
  return (
    <th scope="col" aria-sort={active ? "descending" : "none"} className={`py-1.5 pr-3 font-medium ${align === "right" ? "text-right" : ""}`}>
      <button
        type="button"
        onClick={() => onSort(sort)}
        className={`inline-flex min-h-8 items-center gap-1 rounded-md px-1 -mx-1 hover:text-ink ${active ? "text-ink" : ""}`}
        title={active ? `Sorted by ${label.toLowerCase()}, highest first` : `Sort by ${label.toLowerCase()}`}
      >
        {label}
        <ArrowDown size={12} className={active ? "opacity-100" : "opacity-0"} />
      </button>
    </th>
  );
}

/** Dollar volume with a bar on the heat ramp, scaled to the biggest trader. */
function VolumeCell({ value, max, muted }: { value: string | null; max: number; muted?: boolean }) {
  const n = toNumber(value) ?? 0;
  const share = Math.max(0.02, n / max);
  return (
    <div className="flex flex-col gap-1">
      <span className="num font-medium">{usd(value)}</span>
      <span aria-hidden="true" className="block h-1 w-full rounded-full bg-surface-2">
        <span className={`block h-full rounded-full ${muted ? "bg-line-strong" : "bg-heat-3"}`} style={{ width: `${share * 100}%` }} />
      </span>
    </div>
  );
}

function ProtocolList({ protocols }: { protocols: string[] }) {
  if (protocols.length === 0) return <span className="text-muted">—</span>;
  return (
    <span className="flex flex-wrap gap-1" aria-label={`DEXs: ${protocols.map((p) => protocolName(p)).join(", ")}`}>
      {protocols.map((p) => (
        <Badge key={p} title={protocolName(p)}>
          {protocolName(p, true)}
        </Badge>
      ))}
    </span>
  );
}

function TokenList({ tokens }: { tokens: Trader["top_tokens"] }) {
  if (tokens.length === 0) return <span className="text-muted">—</span>;
  const shown = tokens.slice(0, 3);
  const rest = tokens.length - shown.length;
  return (
    <span className="block max-w-[13rem] truncate" title={tokens.map((t) => `${t.symbol ?? t.token} (${t.trades} trades)`).join(", ")}>
      {shown.map((t, i) => (
        <Fragment key={t.token}>
          {i > 0 && ", "}
          <span className="font-medium">{t.symbol ?? "unknown"}</span>
        </Fragment>
      ))}
      {rest > 0 && <span className="text-muted"> +{rest}</span>}
    </span>
  );
}

function BotGuide() {
  return (
    <details className="group rounded-[10px] border border-line bg-surface">
      <summary className="flex min-h-12 items-center gap-2 px-4 py-3 text-sm font-medium sm:px-5">
        <InfoIcon className="text-muted" />
        How HeatMap tells bots from people
        <ChevronDown className="ml-auto text-muted transition-transform duration-150 group-open:rotate-180" />
      </summary>
      <div className="border-t border-line px-4 py-4 sm:px-5">
        <p className="max-w-prose text-sm leading-relaxed text-muted">
          Each swap is credited to the wallet that signed the transaction. A wallet is set aside as a bot when its
          trading pattern matches one of these. Turn on <span className="font-medium text-ink">Show bots</span> to
          see them, and open any row to see the measurements behind its verdict.
        </p>
        <dl className="mt-4 grid gap-x-8 gap-y-4 md:grid-cols-2">
          {Object.entries(BOT_REASONS).map(([key, r]) => (
            <div key={key}>
              <dt className="text-sm font-medium">{r.title}</dt>
              <dd className="mt-0.5 text-sm leading-relaxed text-muted">{r.summary}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-sm text-muted">
          The biggest people traders are promoted to the{" "}
          <Link href="/watchlist?origin=trader" className="text-primary underline-offset-2 hover:underline">
            watchlist
          </Link>{" "}
          automatically. Use Track to add one yourself.
        </p>
      </div>
    </details>
  );
}
