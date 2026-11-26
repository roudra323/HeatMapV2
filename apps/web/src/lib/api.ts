import type { components } from "./api-types";
import { DEMO, DemoError, demoGet, READ_ONLY_MESSAGE } from "./demo";

export type Schemas = components["schemas"];
export type WalletProfile = Schemas["WalletProfileOut"];
export type WatchEntry = Schemas["WatchlistEntryOut"];
export type WatchPage = Schemas["Page_WatchlistEntryOut_"];
export type Label = Schemas["LabelOut"];
export type Heatmap = Schemas["HeatmapOut"];
export type Network = Schemas["NetworkOut"];
export type NetworkNode = Schemas["NodeOut"];
export type TimelineBucket = Schemas["TimelineBucketOut"];
export type SimilarWallet = Schemas["SimilarWalletOut"];
export type TransferPage = Schemas["Page_TransferOut_"];
export type Cluster = Schemas["ClusterOut"];
export type ClusterPoint = Schemas["ClusterPointOut"];
export type Trader = Schemas["TraderOut"];
export type TraderPage = Schemas["Page_TraderOut_"];
export type Trade = Schemas["TradeOut"];
export type TradePage = Schemas["Page_TradeOut_"];
export type Chain = Schemas["ChainOut"];
export type WatchOrigin = Schemas["WatchOrigin"];

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | undefined>;

function url(path: string, query?: Query): string {
  const u = new URL(path, API_URL);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined) u.searchParams.set(k, String(v));
  }
  return u.toString();
}

async function demoRequest<T>(method: string, path: string, query?: Query): Promise<T> {
  if (method !== "GET") throw new ApiError(403, READ_ONLY_MESSAGE);
  try {
    return await demoGet<T>(path, query);
  } catch (e) {
    throw e instanceof DemoError ? new ApiError(e.status, e.message) : e;
  }
}

async function request<T>(method: string, path: string, query?: Query, body?: unknown): Promise<T> {
  if (DEMO) return demoRequest<T>(method, path, query);
  let res: Response;
  try {
    res = await fetch(url(path, query), {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, `Can't reach the HeatMap API at ${API_URL}. Check that it is running.`);
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((j: { detail?: unknown }) => (typeof j.detail === "string" ? j.detail : res.statusText))
      .catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, query),
  post: <T>(path: string, body: unknown) => request<T>("POST", path, undefined, body),
  delete: (path: string) => request<void>("DELETE", path),
};
