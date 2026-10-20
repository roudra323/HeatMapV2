"use client";

import { useState } from "react";

import { AddWalletForm } from "@/components/AddWalletForm";
import { AddressLink, Chip, Panel, State } from "@/components/ui";
import { api, type WatchPage } from "@/lib/api";
import { date } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const PAGE = 50;

export default function WatchlistPage() {
  const [origin, setOrigin] = useState<string>("");
  const [offset, setOffset] = useState(0);
  const list = useApi<WatchPage>("/v1/watchlist", {
    origin: origin || undefined,
    active: true,
    limit: PAGE,
    offset,
  });

  async function untrack(address: string) {
    await api.delete(`/v1/watchlist/${address}`);
    list.reload();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Watchlist</h1>
      <Panel title="Track a wallet">
        <AddWalletForm onAdded={list.reload} />
      </Panel>
      <Panel
        title={`Tracked wallets${list.data ? ` (${list.data.total})` : ""}`}
        action={
          <select
            value={origin}
            onChange={(e) => {
              setOrigin(e.target.value);
              setOffset(0);
            }}
            className="rounded-md border border-line bg-bg px-2 py-1 text-xs"
          >
            <option value="">all</option>
            <option value="seed">seeds</option>
            <option value="neighbour">neighbours</option>
          </select>
        }
      >
        <State
          loading={list.loading}
          error={list.error}
          empty={list.data?.items.length === 0 ? "Nothing tracked yet." : undefined}
        />
        {list.data && list.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1">Wallet</th>
                  <th>Origin</th>
                  <th>Found via</th>
                  <th>Synced to block</th>
                  <th>Last sync</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((w) => (
                  <tr key={w.address} className="border-t border-line">
                    <td className="py-1.5">
                      <AddressLink address={w.address} />
                      {w.note && <span className="ml-2 text-xs text-muted">{w.note}</span>}
                    </td>
                    <td>
                      <Chip tone={w.origin === "seed" ? "accent" : "default"}>
                        {w.origin === "seed" ? "seed" : `hop ${w.hop}`}
                      </Chip>
                    </td>
                    <td>{w.via_address ? <AddressLink address={w.via_address} /> : "—"}</td>
                    <td className="mono">{w.last_block ?? "pending"}</td>
                    <td className={w.last_error ? "text-danger" : ""} title={w.last_error ?? undefined}>
                      {w.last_error ? "error" : date(w.last_synced_at)}
                    </td>
                    <td className="text-right">
                      <button
                        onClick={() => untrack(w.address)}
                        className="text-xs text-muted hover:text-danger"
                      >
                        untrack
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3 flex justify-between text-xs">
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
                className="disabled:opacity-40"
              >
                ← previous
              </button>
              <button
                disabled={offset + PAGE >= list.data.total}
                onClick={() => setOffset(offset + PAGE)}
                className="disabled:opacity-40"
              >
                next →
              </button>
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
