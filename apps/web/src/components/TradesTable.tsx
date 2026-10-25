"use client";

import { Fragment, useState } from "react";

import type { Trade, TradePage } from "@/lib/api";
import { protocolName } from "@/lib/copy";
import { dateTime, num, relativeTime, shortAddress, tokenAmount, usd } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useExplorer } from "@/lib/useExplorer";
import { useNow } from "@/lib/useNow";

import { ArrowRight, ExternalIcon, SwapIcon } from "./icons";
import { Async, Badge, EmptyState, Pagination, Panel, SkeletonRows } from "./ui";

const PAGE = 25;

type Group = { hash: string; trades: Trade[] };

/** Swaps from one transaction arrive next to each other; keep them together. */
function groupByTx(trades: Trade[]): Group[] {
  const groups: Group[] = [];
  for (const t of trades) {
    const last = groups.at(-1);
    if (last && last.hash === t.tx_hash) last.trades.push(t);
    else groups.push({ hash: t.tx_hash, trades: [t] });
  }
  return groups;
}

function Token({ symbol, address }: { symbol: string | null; address: string }) {
  return symbol ? (
    <span className="font-medium">{symbol}</span>
  ) : (
    <span className="mono text-muted" title={address}>
      {shortAddress(address)}
    </span>
  );
}

function SwapCell({ t }: { t: Trade }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
      <span className="num whitespace-nowrap">
        {tokenAmount(t.amount_in)} <Token symbol={t.token_in_symbol} address={t.token_in} />
      </span>
      <ArrowRight size={14} className="shrink-0 text-muted" />
      <span className="sr-only">for</span>
      <span className="num whitespace-nowrap">
        {tokenAmount(t.amount_out)} <Token symbol={t.token_out_symbol} address={t.token_out} />
      </span>
    </span>
  );
}

function TxLink({ hash, explorer }: { hash: string; explorer: string | null }) {
  if (!explorer) return <span className="mono text-muted">{shortAddress(hash)}</span>;
  return (
    <a
      href={`${explorer}/tx/${hash}`}
      target="_blank"
      rel="noreferrer"
      title={`View ${hash} on the block explorer`}
      className="mono inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
    >
      {shortAddress(hash)}
      <ExternalIcon size={12} />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}

/** Swaps this wallet signed on the DEXs HeatMap reads, newest first. */
export function TradesPanel({ address }: { address: string }) {
  const [offset, setOffset] = useState(0);
  const trades = useApi<TradePage>(`/v1/wallets/${address}/trades`, { limit: PAGE, offset });
  const explorer = useExplorer();
  const now = useNow();

  return (
    <Panel
      flush
      title={
        <span className="flex items-center gap-2">
          DEX trades
          {trades.data && trades.data.total > 0 && (
            <span className="num text-sm font-normal text-muted">{num(trades.data.total)}</span>
          )}
        </span>
      }
      description="Swaps this wallet signed itself on Uniswap and SushiSwap, newest first. Swaps from one transaction are grouped."
    >
      <Async
        state={trades}
        skeleton={<SkeletonRows rows={6} className="px-5 pb-4" />}
        isEmpty={(d) => d.items.length === 0}
        empty={
          <div className="px-4 pb-4 sm:px-5">
            <EmptyState icon={<SwapIcon size={20} />} title="No DEX trades recorded" compact>
              HeatMap only records swaps where this wallet signed the transaction. Trades placed through intent
              protocols such as CoW Swap are credited to the solver that settled them.
            </EmptyState>
          </div>
        }
      >
        {(page) => {
          const groups = groupByTx(page.items);
          return (
            <>
              <div className="hidden md:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-y border-line text-left text-xs text-muted">
                      <th scope="col" className="py-2.5 pr-3 pl-5 font-medium">When</th>
                      <th scope="col" className="py-2.5 pr-3 font-medium">
                        Swap <span className="font-normal">(paid, then received)</span>
                      </th>
                      <th scope="col" className="py-2.5 pr-3 text-right font-medium">Value</th>
                      <th scope="col" className="py-2.5 pr-3 font-medium">DEX</th>
                      <th scope="col" className="py-2.5 pr-5 font-medium">Transaction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => (
                      <Fragment key={`${g.hash}-${g.trades[0]!.log_index}`}>
                        {g.trades.map((t, i) => (
                          <tr
                            key={`${t.tx_hash}-${t.log_index}`}
                            className={`align-top hover:bg-surface-2 ${i === g.trades.length - 1 ? "border-b border-line" : ""}`}
                          >
                            {i === 0 && (
                              <td rowSpan={g.trades.length} className="py-2.5 pr-3 pl-5 whitespace-nowrap text-muted" title={dateTime(t.block_time)}>
                                {relativeTime(t.block_time, now)}
                              </td>
                            )}
                            <td className="py-2.5 pr-3">
                              <SwapCell t={t} />
                            </td>
                            <td className="num py-2.5 pr-3 text-right whitespace-nowrap">{usd(t.amount_usd)}</td>
                            <td className="py-2.5 pr-3 whitespace-nowrap" title={`Pool ${t.pool_id}`}>
                              {protocolName(t.protocol)}
                            </td>
                            {i === 0 && (
                              <td rowSpan={g.trades.length} className="py-2.5 pr-5">
                                <div className="flex flex-col items-start gap-1">
                                  <TxLink hash={t.tx_hash} explorer={explorer} />
                                  {g.trades.length > 1 && <Badge>{g.trades.length} swaps</Badge>}
                                </div>
                              </td>
                            )}
                          </tr>
                        ))}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>

              <ul className="divide-y divide-line border-t border-line md:hidden">
                {groups.map((g) => (
                  <li key={`${g.hash}-${g.trades[0]!.log_index}`} className="space-y-2 px-4 py-3">
                    <div className="flex items-center justify-between gap-3 text-xs text-muted">
                      <span title={dateTime(g.trades[0]!.block_time)}>{relativeTime(g.trades[0]!.block_time, now)}</span>
                      <TxLink hash={g.hash} explorer={explorer} />
                    </div>
                    {g.trades.map((t) => (
                      <div key={t.log_index} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
                        <SwapCell t={t} />
                        <span className="num text-muted">
                          {usd(t.amount_usd)}, {protocolName(t.protocol, true)}
                        </span>
                      </div>
                    ))}
                  </li>
                ))}
              </ul>

              <div className="border-t border-line">
                <Pagination offset={offset} limit={PAGE} total={page.total} noun="swaps" onChange={setOffset} />
              </div>
            </>
          );
        }}
      </Async>
    </Panel>
  );
}
