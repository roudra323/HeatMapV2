"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { AddWalletForm } from "@/components/AddWalletForm";
import { AlertIcon, CompassIcon, EyeIcon } from "@/components/icons";
import { OriginBadge } from "@/components/OriginBadge";
import {
  AddressLink,
  Async,
  Badge,
  Button,
  buttonClass,
  EmptyState,
  PageHeader,
  Pagination,
  Panel,
  Segmented,
  SkeletonRows,
} from "@/components/ui";
import { api, type WatchEntry, type WatchPage } from "@/lib/api";
import { ORIGINS } from "@/lib/copy";
import { date, dateTime, num, relativeTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useNow } from "@/lib/useNow";

const PAGE = 50;
type OriginFilter = "" | "seed" | "trader" | "neighbour";
const FILTERS: OriginFilter[] = ["", "seed", "trader", "neighbour"];

const FILTER_LABEL: Record<OriginFilter, string> = {
  "": "All",
  seed: "Seeds",
  trader: "Discovered traders",
  neighbour: "Neighbours",
};

export function WatchlistView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const originParam = params.get("origin") ?? "";
  const origin: OriginFilter = FILTERS.includes(originParam as OriginFilter) ? (originParam as OriginFilter) : "";
  const [offset, setOffset] = useState(0);
  const [showAdd, setShowAdd] = useState(false);

  const list = useApi<WatchPage>("/v1/watchlist", { origin: origin || undefined, active: true, limit: PAGE, offset });
  const counts = {
    "": useApi<WatchPage>("/v1/watchlist", { active: true, limit: 1 }),
    seed: useApi<WatchPage>("/v1/watchlist", { origin: "seed", active: true, limit: 1 }),
    trader: useApi<WatchPage>("/v1/watchlist", { origin: "trader", active: true, limit: 1 }),
    neighbour: useApi<WatchPage>("/v1/watchlist", { origin: "neighbour", active: true, limit: 1 }),
  };

  function setOrigin(next: OriginFilter) {
    setOffset(0);
    router.replace(next ? `${pathname}?origin=${next}` : pathname, { scroll: false });
  }
  function reloadAll() {
    list.reload();
    Object.values(counts).forEach((c) => c.reload());
  }

  const total = counts[""].data?.total;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Watchlist"
        description="The wallets HeatMap syncs and profiles. They arrive three ways: seeds you add by hand, the biggest human traders promoted from Discover, and neighbours found around tracked wallets."
        actions={
          <Button variant={showAdd ? "secondary" : "primary"} onClick={() => setShowAdd((v) => !v)} aria-expanded={showAdd} aria-controls="add-wallet">
            {showAdd ? "Close" : "Track a wallet"}
          </Button>
        }
      />

      {showAdd && (
        <Panel id="add-wallet" title="Track a wallet" description="Add a seed wallet by address. HeatMap will sync its history and look for its neighbours.">
          <AddWalletForm onAdded={reloadAll} />
        </Panel>
      )}

      <Panel flush>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
          <Segmented
            label="Show wallets by how they were added"
            value={origin}
            onChange={setOrigin}
            options={FILTERS.map((f) => ({
              value: f,
              label: (
                <>
                  {FILTER_LABEL[f]}
                  {counts[f].data && <span className="num ml-1.5 text-muted">{num(counts[f].data!.total)}</span>}
                </>
              ),
            }))}
          />
          {origin && <p className="text-[0.8125rem] text-muted">{ORIGINS[origin].summary}</p>}
        </div>

        <Async
          state={list}
          skeleton={<SkeletonRows rows={8} className="p-5" />}
          isEmpty={(d) => d.items.length === 0}
          empty={
            <div className="p-5">
              <EmptyState
                icon={<EyeIcon size={22} />}
                title={total === 0 ? "Nothing tracked yet" : `No ${FILTER_LABEL[origin].toLowerCase()} on the watchlist`}
                action={
                  <>
                    <Link href="/discover" className={buttonClass("primary", "sm")}>
                      <CompassIcon size={14} />
                      Discover traders
                    </Link>
                    <Button size="sm" onClick={() => setShowAdd(true)}>
                      Add a wallet by address
                    </Button>
                  </>
                }
              >
                {origin === "neighbour"
                  ? "Neighbours are added when the expansion job runs over tracked wallets that have synced."
                  : origin === "trader"
                    ? "Traders are promoted automatically when the discovery job finds big human traders, or when you track one from Discover."
                    : "Start from Discover to pick big human traders, or add a wallet you already know."}
              </EmptyState>
            </div>
          }
        >
          {(page) => (
            <>
              <WatchTable items={page.items} onChanged={reloadAll} />
              <div className="border-t border-line">
                <Pagination offset={offset} limit={PAGE} total={page.total} noun="wallets" onChange={setOffset} />
              </div>
            </>
          )}
        </Async>
      </Panel>
    </div>
  );
}

function HowAdded({ entry }: { entry: WatchEntry }) {
  return (
    <div className="flex flex-col items-start gap-1">
      <OriginBadge entry={entry} />
      {entry.origin === "neighbour" && (
        <span className="text-xs text-muted">
          {entry.hop === 1 ? "1 hop" : `${entry.hop} hops`}
          {entry.via_address && (
            <>
              {" "}from <AddressLink address={entry.via_address} />
            </>
          )}
        </span>
      )}
    </div>
  );
}

function SyncStatus({ entry, now }: { entry: WatchEntry; now: number }) {
  if (entry.last_error) {
    return (
      <div className="flex flex-col items-start gap-1">
        <Badge tone="danger" icon={<AlertIcon size={12} />}>
          Sync failed
        </Badge>
        <span className="line-clamp-2 max-w-64 text-xs text-muted" title={entry.last_error}>
          {entry.last_error}
        </span>
      </div>
    );
  }
  if (!entry.last_synced_at) return <span className="text-muted">Waiting for first sync</span>;
  return (
    <div className="flex flex-col">
      <span title={dateTime(entry.last_synced_at)}>Synced {relativeTime(entry.last_synced_at, now)}</span>
      {entry.last_block !== null && entry.last_block !== undefined && (
        <span className="num text-xs text-muted">to block {entry.last_block.toLocaleString("en-US")}</span>
      )}
    </div>
  );
}

function UntrackButton({ address, onDone }: { address: string; onDone: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  if (!confirming) {
    return (
      <Button size="sm" variant="ghost" onClick={() => setConfirming(true)} aria-label={`Untrack ${address}`}>
        Untrack
      </Button>
    );
  }
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <span className="inline-flex gap-1.5">
        <Button size="sm" variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>
          Cancel
        </Button>
        <Button
          size="sm"
          variant="danger"
          busy={busy}
          autoFocus
          onClick={async () => {
            setBusy(true);
            setError(undefined);
            try {
              await api.delete(`/v1/watchlist/${address}`);
              onDone();
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
              setBusy(false);
            }
          }}
        >
          Confirm untrack
        </Button>
      </span>
      {error && (
        <span role="alert" className="text-xs text-danger">
          {error}
        </span>
      )}
    </span>
  );
}

function WatchTable({ items, onChanged }: { items: WatchEntry[]; onChanged: () => void }) {
  const now = useNow();
  return (
    <>
      <div className="hidden md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th scope="col" className="py-2.5 pr-3 pl-5 font-medium">Wallet</th>
              <th scope="col" className="py-2.5 pr-3 font-medium">How it was added</th>
              <th scope="col" className="py-2.5 pr-3 font-medium">Added</th>
              <th scope="col" className="py-2.5 pr-3 font-medium">History sync</th>
              <th scope="col" className="py-2.5 pr-5 text-right font-medium">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((w) => (
              <tr key={w.address} className="border-b border-line align-top last:border-b-0 hover:bg-surface-2">
                <td className="py-3 pr-3 pl-5">
                  <AddressLink address={w.address} />
                  {w.note && <p className="mt-0.5 max-w-64 text-xs text-muted">{w.note}</p>}
                </td>
                <td className="py-3 pr-3">
                  <HowAdded entry={w} />
                </td>
                <td className="num py-3 pr-3 whitespace-nowrap text-muted">{date(w.created_at)}</td>
                <td className="py-3 pr-3">
                  <SyncStatus entry={w} now={now} />
                </td>
                <td className="py-2 pr-5 text-right">
                  <UntrackButton address={w.address} onDone={onChanged} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="divide-y divide-line md:hidden">
        {items.map((w) => (
          <li key={w.address} className="space-y-2.5 px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <AddressLink address={w.address} />
                {w.note && <p className="mt-0.5 text-xs text-muted">{w.note}</p>}
              </div>
              <UntrackButton address={w.address} onDone={onChanged} />
            </div>
            <HowAdded entry={w} />
            <div className="text-sm">
              <SyncStatus entry={w} now={now} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
