/**
 * Demo mode: answers API requests from a static snapshot in `public/demo`, so the
 * app runs without the API or PostgreSQL (e.g. on Vercel). Enabled by
 * NEXT_PUBLIC_DEMO=1. The snapshot comes from `make snapshot`
 * (`heatmap_api.snapshot`), which exports what the real API returns for the
 * synthetic `heatmap demo` dataset.
 *
 * Lists are exported whole; filters, sorting and paging happen here, following
 * the API's own rules. Writes are refused: the demo is read-only.
 */
import type { Trade, Trader, WatchEntry } from "./api";

export const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

export const READ_ONLY_MESSAGE = "This is a read-only demo. Run HeatMap locally to track wallets.";

type Query = Record<string, string | number | boolean | undefined>;

interface Response {
  status: number;
  body: unknown;
}

interface WalletFile {
  profile: Record<string, Response>;
  heatmap: Response;
  timeline: Response;
  neighbors: Record<string, Response>;
  similar: Response;
  trades: Trade[];
  transfers: unknown[];
}

export class DemoError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const files = new Map<string, Promise<unknown>>();

function load<T>(name: string): Promise<T> {
  let file = files.get(name);
  if (!file) {
    file = fetch(`/demo/${name}`).then((res) => {
      if (res.status === 404) return null;
      if (!res.ok) throw new DemoError(res.status, `Demo data ${name} failed to load.`);
      return res.json();
    });
    file.catch(() => files.delete(name));
    files.set(name, file);
  }
  return file as Promise<T>;
}

export interface DemoMeta {
  generated_at: string;
  chain: string;
}

export const demoMeta = () => load<DemoMeta>("meta.json");

function page<T>(items: T[], query: Query) {
  const limit = Math.min(Number(query.limit ?? 50), 500);
  const offset = Number(query.offset ?? 0);
  return { total: items.length, limit, offset, items: items.slice(offset, offset + limit) };
}

const flag = (v: Query[string]) => v === true || v === "true";

function traders(all: Trader[], query: Query) {
  const min = query.min_volume_usd === undefined ? undefined : Number(query.min_volume_usd);
  const rows = all.filter(
    (t) =>
      (flag(query.include_bots) || !t.is_bot) &&
      (min === undefined || Number(t.volume_usd ?? 0) >= min) &&
      (!query.protocol || t.protocols.includes(String(query.protocol))),
  );
  // Same order as the API: the sort key descending, then the address.
  const key: (t: Trader) => number =
    query.sort === "tx_count"
      ? (t) => t.tx_count
      : query.sort === "last_trade"
        ? (t) => Date.parse(t.last_trade_at)
        : (t) => (t.volume_usd === null ? -Infinity : Number(t.volume_usd));
  rows.sort((a, b) => key(b) - key(a) || a.address.localeCompare(b.address));
  return page(rows, query);
}

function watchlist(all: WatchEntry[], query: Query) {
  const active = query.active === undefined ? undefined : flag(query.active);
  const rows = all.filter(
    (e) => (!query.origin || e.origin === query.origin) && (active === undefined || e.active === active),
  );
  return page(rows, query); // exported in the API's order
}

function unwrap(res: Response | undefined): unknown {
  if (!res) throw new DemoError(404, "Not in the demo data.");
  if (res.status >= 400) {
    const detail = (res.body as { detail?: unknown } | null)?.detail;
    throw new DemoError(res.status, typeof detail === "string" ? detail : "Not in the demo data.");
  }
  return res.body;
}

async function wallet(address: string, part: string | undefined, query: Query): Promise<unknown> {
  const data = await load<WalletFile | null>(`wallets/${address.toLowerCase()}.json`);
  if (!data) throw new DemoError(404, "wallet not found");
  switch (part) {
    case undefined:
      return unwrap(data.profile[String(query.window ?? "all")]);
    case "heatmap":
      return unwrap(data.heatmap);
    case "timeline":
      return unwrap(data.timeline);
    case "neighbors":
      return unwrap(data.neighbors[String(query.depth ?? 1)]);
    case "similar":
      return unwrap(data.similar);
    case "trades":
      return page(data.trades, query);
    case "transfers":
      return page(data.transfers, query);
    default:
      throw new DemoError(404, "Not in the demo data.");
  }
}

const STATIC: Record<string, (q: Query) => string> = {
  "/v1/chains": () => "chains.json",
  "/v1/tags": () => "tags.json",
  "/v1/clusters": () => "clusters.json",
  "/v1/clusters/points": () => "cluster-points.json",
  "/v1/heatmaps/segments": (q) => `segments-${q.by === "tag" ? "tag" : "cluster"}.json`,
};

export async function demoGet<T>(path: string, query: Query = {}): Promise<T> {
  if (path === "/v1/traders") return traders(await load<Trader[]>("traders.json"), query) as T;
  if (path === "/v1/watchlist") return watchlist(await load<WatchEntry[]>("watchlist.json"), query) as T;
  const file = STATIC[path];
  if (file) return (await load<T>(file(query))) as T;
  const [, address, part] = /^\/v1\/wallets\/(0x[0-9a-fA-F]{40})(?:\/(\w+))?$/.exec(path) ?? [];
  if (address) return (await wallet(address, part, query)) as T;
  throw new DemoError(404, "Not in the demo data.");
}
