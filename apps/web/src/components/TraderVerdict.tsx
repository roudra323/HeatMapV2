"use client";

import Link from "next/link";

import type { Trader } from "@/lib/api";
import { botReason, humanVerdict, traderSignals } from "@/lib/copy";
import { date, num, usd } from "@/lib/format";

import { BotIcon, CheckIcon } from "./icons";
import { Badge, buttonClass, Meter } from "./ui";

export function BotBadge({ reason }: { reason: string | null }) {
  const info = botReason(reason);
  return (
    <Badge tone="bot" icon={<BotIcon size={12} />}>
      {info ? `Bot: ${info.title.toLowerCase()}` : "Bot"}
    </Badge>
  );
}

/** Why the pipeline counts this wallet as a bot or a person, with the measurements behind it. */
export function TraderVerdict({ trader }: { trader: Trader }) {
  const info = botReason(trader.bot_reason);
  const decisive = trader.is_bot ? info?.signal : "router";
  const signals = traderSignals(trader);
  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-3">
        {trader.is_bot ? (
          <>
            <p className="flex items-center gap-2 text-sm font-medium">
              <BotIcon className="text-bot" />
              Filtered out as a bot{info ? `: ${info.title.toLowerCase()}` : ""}
            </p>
            {info && <p className="text-sm leading-relaxed text-muted">{info.summary}</p>}
          </>
        ) : (
          <>
            <p className="flex items-center gap-2 text-sm font-medium">
              <CheckIcon className="text-ok" />
              Looks like a person
            </p>
            <p className="text-sm leading-relaxed text-muted">{humanVerdict(trader)}</p>
          </>
        )}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <dt className="text-xs text-muted">First trade seen</dt>
            <dd className="num">{date(trader.first_trade_at)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Largest single trade</dt>
            <dd className="num">{usd(trader.max_tx_usd)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Distinct tokens</dt>
            <dd className="num">{num(trader.distinct_tokens)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Top tokens by trades</dt>
            <dd>
              {trader.top_tokens.length === 0
                ? "—"
                : trader.top_tokens.map((t) => `${t.symbol ?? "unknown"} (${t.trades})`).join(", ")}
            </dd>
          </div>
        </dl>
        <Link href={`/wallets/${trader.address}`} className={buttonClass("secondary", "sm")}>
          Open wallet
        </Link>
      </div>
      <div className="min-w-0">
        <p className="mb-2 text-xs font-medium text-muted">How its transactions break down</p>
        <ul className="space-y-2.5">
          {signals.map((s) => {
            const key = s.key === decisive;
            return (
              <li key={s.key} className="grid grid-cols-[minmax(0,1fr)_3.5rem] items-center gap-x-3 gap-y-1">
                <span className={`text-[0.8125rem] ${key ? "font-medium text-ink" : "text-muted"}`}>
                  {s.label}
                  {key && <span className="sr-only"> (deciding signal)</span>}
                </span>
                <span className={`num text-right text-[0.8125rem] ${key ? "font-medium" : ""}`}>{s.value}</span>
                <span className="col-span-2">
                  <Meter value={s.share} tone={key ? (trader.is_bot ? "heat" : "primary") : "muted"} />
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
