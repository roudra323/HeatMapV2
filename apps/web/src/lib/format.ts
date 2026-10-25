/** Display formatting. Decimals arrive from the API as strings, so everything accepts both. */

const DASH = "—";

export function toNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function shortAddress(address: string): string {
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}

/** US dollars; compact from $1M up, whole dollars from $100 up. */
export function usd(value: unknown): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  if (n !== 0 && Math.abs(n) < 0.01) return n < 0 ? "-<$0.01" : "<$0.01";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    notation: Math.abs(n) >= 1e6 ? "compact" : "standard",
    maximumFractionDigits: Math.abs(n) >= 1e6 ? 1 : Math.abs(n) >= 100 ? 0 : 2,
  });
}

/** Always-compact dollars for headline figures: $105K, $4.2M. */
export function usdCompact(value: unknown): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: Math.abs(n) >= 1000 ? 1 : 0,
  });
}

export function num(value: unknown, digits = 0): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return n.toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function pct(value: unknown, digits = 0): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return `${(n * 100).toFixed(digits)}%`;
}

/** Token quantities: enough significant digits to be useful, never 18 decimals. */
export function tokenAmount(value: unknown): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const abs = Math.abs(n);
  if (abs === 0) return "0";
  if (abs >= 1e6) {
    return n.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 2 });
  }
  if (abs >= 1) return n.toLocaleString("en-US", { maximumFractionDigits: abs >= 1000 ? 0 : 4 });
  if (abs < 1e-6) return "<0.000001";
  return n.toLocaleString("en-US", { maximumSignificantDigits: 4 });
}

export function date(value: string | null | undefined): string {
  if (!value) return DASH;
  return new Date(value).toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return DASH;
  return new Date(value).toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const RELATIVE = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "3 hours ago". Falls back to a date when ``now`` is unknown (server render). */
export function relativeTime(value: string | null | undefined, now: number): string {
  if (!value) return DASH;
  if (!now) return date(value);
  const seconds = (new Date(value).getTime() - now) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return RELATIVE.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

export function humanize(key: string): string {
  return key.replace(/^share_/, "").replaceAll("_", " ");
}

/** Sentence-case a snake_case identifier: "behaviour_changed" → "Behaviour changed". */
export function sentence(key: string): string {
  const text = humanize(key);
  return text.charAt(0).toUpperCase() + text.slice(1);
}
