import Link from "next/link";
import type { ReactNode } from "react";

import { shortAddress } from "@/lib/format";

export function Panel({
  title,
  action,
  children,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-lg border border-line bg-panel p-4">
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-3" title={hint}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mono mt-1 text-lg">{value}</div>
    </div>
  );
}

export function Chip({ children, tone = "default", title }: {
  children: ReactNode;
  tone?: "default" | "accent" | "danger";
  title?: string;
}) {
  const tones = {
    default: "border-line text-muted",
    accent: "border-accent/40 bg-accent-soft text-accent",
    danger: "border-danger/40 text-danger",
  } as const;
  return (
    <span title={title} className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function AddressLink({ address, label }: { address: string; label?: string | null }) {
  return (
    <Link href={`/wallets/${address}`} className="mono text-sm hover:text-accent" title={address}>
      {label ?? shortAddress(address)}
    </Link>
  );
}

export function State({ loading, error, empty }: { loading?: boolean; error?: string; empty?: string }) {
  if (loading) return <p className="text-sm text-muted">Loading…</p>;
  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (empty) return <p className="text-sm text-muted">{empty}</p>;
  return null;
}
