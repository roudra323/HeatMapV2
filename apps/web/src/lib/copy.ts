/**
 * Plain-language explanations of what the pipeline decided and why.
 * Wording mirrors the rules in heatmap_core (dex/traders.py, models/tags.py).
 */

import type { Trader } from "./api";
import { num, pct, shortAddress } from "./format";

export type BotReason =
  | "settlement_signer"
  | "private_contract"
  | "arbitrage"
  | "batch_executor"
  | "high_frequency";

export interface Signal {
  key: string;
  label: string;
  value: string;
  /** 0..1, for the meter. */
  share: number;
}

export const BOT_REASONS: Record<BotReason, { title: string; summary: string; signal: string }> = {
  settlement_signer: {
    title: "Settles others' orders",
    summary:
      "Most of its transactions settle orders placed through intent protocols such as CoW Swap or UniswapX. The signer is a solver or filler executing trades for other people, not a trader itself.",
    signal: "settlement",
  },
  private_contract: {
    title: "Trades through its own contract",
    summary:
      "Most of its swaps go straight to a pool, or through a contract that only a few wallets use. That is how MEV and arbitrage bots operate. People trade through public routers and apps.",
    signal: "private",
  },
  arbitrage: {
    title: "Circular arbitrage",
    summary:
      "In many of its transactions it buys back every token it sold, within the same transaction. That loop captures price gaps between pools rather than taking a position.",
    signal: "arbitrage",
  },
  batch_executor: {
    title: "Batches many swaps",
    summary:
      "It packs many swaps into each transaction, which is typical of solvers and market makers settling orders in bulk.",
    signal: "swaps",
  },
  high_frequency: {
    title: "Trades around the clock",
    summary:
      "It trades far more often per active day than a person trading by hand could.",
    signal: "per_day",
  },
};

export function botReason(reason: string | null | undefined) {
  return reason && reason in BOT_REASONS ? BOT_REASONS[reason as BotReason] : undefined;
}

export function tradesPerDay(t: Trader): number {
  return t.tx_count / Math.max(t.active_days, 1);
}

/** The measurements behind a verdict, in the order a reader should scan them. */
export function traderSignals(t: Trader): Signal[] {
  const perDay = tradesPerDay(t);
  return [
    { key: "router", label: "Through public routers and apps", value: pct(t.router_share), share: t.router_share },
    { key: "private", label: "Direct to pools or private contracts", value: pct(t.private_share), share: t.private_share },
    { key: "settlement", label: "Settling other people's orders", value: pct(t.settlement_share), share: t.settlement_share },
    { key: "arbitrage", label: "Circular (arbitrage) transactions", value: pct(t.arbitrage_share), share: t.arbitrage_share },
    {
      key: "swaps",
      label: "Swaps per transaction",
      value: num(t.swaps_per_tx, 1),
      share: Math.min(1, (t.swaps_per_tx - 1) / 9),
    },
    {
      key: "per_day",
      label: "Trades per active day",
      value: num(perDay, 1),
      share: Math.min(1, perDay / 150),
    },
  ];
}

/** One sentence on why a trader counts as a person. */
export function humanVerdict(t: Trader): string {
  const parts = [`${pct(t.router_share)} of its transactions go through public routers and apps`];
  parts.push(
    t.swaps_per_tx < 1.5
      ? "it makes one swap per transaction"
      : `it averages ${num(t.swaps_per_tx, 1)} swaps per transaction`,
  );
  parts.push(`${num(tradesPerDay(t), 1)} trades per active day`);
  return `Counted as a person: ${parts.join(", ")}.`;
}

export const PROTOCOLS: Record<string, { name: string; short: string }> = {
  uniswap_v2: { name: "Uniswap v2", short: "Uni v2" },
  uniswap_v3: { name: "Uniswap v3", short: "Uni v3" },
  uniswap_v4: { name: "Uniswap v4", short: "Uni v4" },
  sushiswap: { name: "SushiSwap", short: "Sushi" },
};

export function protocolName(p: string, short = false): string {
  const known = PROTOCOLS[p];
  if (known) return short ? known.short : known.name;
  return p.replaceAll("_", " ");
}

export const ORIGINS = {
  seed: { label: "Seed", summary: "Added by hand as a starting point." },
  trader: {
    label: "Discovered trader",
    summary: "Promoted from DEX trades as one of the biggest human traders.",
  },
  neighbour: {
    label: "Neighbour",
    summary: "Found because it trades often with a tracked wallet.",
  },
} as const;

export type Origin = keyof typeof ORIGINS;

export function originOf(origin: string): (typeof ORIGINS)[Origin] {
  return ORIGINS[(origin in ORIGINS ? origin : "seed") as Origin];
}

export function neighbourPath(hop: number, via: string | null): string {
  const hops = hop === 1 ? "1 hop" : `${hop} hops`;
  return via ? `${hops} from ${shortAddress(via)}` : hops;
}

export const TAGS: Record<string, { title: string; summary: string; risk?: boolean }> = {
  stablecoin_heavy: { title: "Stablecoin heavy", summary: "Half or more of its transfers are stablecoins." },
  nft_trader: { title: "NFT trader", summary: "A large share of its transfers are NFTs." },
  meme_trader: { title: "Meme trader", summary: "A large share of its transfers are meme tokens." },
  liquid_staker: { title: "Liquid staker", summary: "Holds and moves liquid staking tokens." },
  dex_trader: { title: "DEX trader", summary: "Trades regularly through DEX routers." },
  cex_user: { title: "Exchange user", summary: "Moves funds to and from centralised exchanges." },
  bridge_user: { title: "Bridge user", summary: "Uses bridges to move funds between chains." },
  lending_user: { title: "Lending user", summary: "Supplies or borrows on lending markets." },
  whale: { title: "Whale", summary: "Has moved at least $1M." },
  bot_like: { title: "Bot-like", summary: "Transacts at machine-regular intervals or volumes.", risk: true },
  dormant: { title: "Dormant", summary: "No activity for 90 days or more." },
  new_wallet: { title: "New wallet", summary: "First and last activity less than 30 days apart." },
  distributor: { title: "Distributor", summary: "Sends to many distinct addresses and rarely receives." },
  collector: { title: "Collector", summary: "Receives from many distinct addresses and rarely sends." },
  sybil_suspect: {
    title: "Sybil suspect",
    summary: "Shares funders, counterparties or timing with other tracked wallets.",
    risk: true,
  },
  mixer_exposure: { title: "Mixer exposure", summary: "Some transfers touch a mixer.", risk: true },
};

export function tagInfo(tag: string) {
  return TAGS[tag] ?? { title: tag.replaceAll("_", " "), summary: "" };
}
