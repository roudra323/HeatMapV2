"use client";

import Link from "next/link";
import { useId, useState, type ButtonHTMLAttributes, type ReactNode } from "react";

import { shortAddress } from "@/lib/format";
import type { ApiState } from "@/lib/useApi";

import { AlertIcon, CheckIcon, ChevronLeft, ChevronRight, CopyIcon, RefreshIcon, SpinnerIcon } from "./icons";

/* ---------------------------------------------------------------- layout */

export function PageHeader({
  title,
  description,
  actions,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4 pb-6">
      <div className="min-w-0 max-w-3xl">
        <h1 className="text-[1.625rem] leading-tight font-semibold tracking-[-0.015em] sm:text-[1.875rem]">
          {title}
        </h1>
        {description && <p className="mt-2 text-[0.9375rem] leading-relaxed text-muted">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  description,
  action,
  children,
  flush = false,
  className = "",
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  /** Let tables run edge to edge. */
  flush?: boolean;
  className?: string;
  id?: string;
}) {
  const headingId = useId();
  return (
    <section
      id={id}
      aria-labelledby={title ? headingId : undefined}
      className={`min-w-0 rounded-[10px] border border-line bg-surface ${className}`}
    >
      {(title || action) && (
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 pt-4 pb-3 sm:px-5">
          <div className="min-w-0">
            {title && (
              <h2 id={headingId} className="text-[0.9375rem] font-semibold">
                {title}
              </h2>
            )}
            {description && <p className="mt-0.5 text-sm leading-relaxed text-muted">{description}</p>}
          </div>
          {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
        </div>
      )}
      <div className={flush ? "pb-1" : "px-4 pb-5 sm:px-5"}>{children}</div>
    </section>
  );
}

/** A row of headline figures in one hairline-divided strip. */
export function StatStrip({
  items,
  className = "",
}: {
  items: { label: string; value: ReactNode; hint?: ReactNode; loading?: boolean }[];
  className?: string;
}) {
  const cols = items.length >= 4 ? "sm:grid-cols-4" : items.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2";
  const wide = items.length > 4 ? "lg:grid-cols-6" : "";
  return (
    <dl
      className={`grid grid-cols-2 gap-px overflow-hidden rounded-[10px] border border-line bg-line ${cols} ${wide} ${className}`}
    >
      {items.map((item) => (
        <div key={item.label} className="flex min-w-0 flex-col bg-surface px-4 py-3.5 sm:px-5">
          <dt className="text-[0.8125rem] text-muted">{item.label}</dt>
          <dd className="num mt-1 text-[1.375rem] leading-tight font-semibold tracking-[-0.01em]">
            {item.loading ? <Skeleton className="mt-1 h-6 w-20" /> : item.value}
          </dd>
          {item.hint && !item.loading && <dd className="mt-1 text-xs leading-snug text-muted">{item.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}

/* ---------------------------------------------------------------- controls */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

export function buttonClass(variant: ButtonVariant = "secondary", size: ButtonSize = "md"): string {
  const base =
    "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors duration-150 disabled:opacity-50";
  const sizes = {
    sm: "min-h-8 px-2.5 text-[0.8125rem]",
    md: "min-h-10 px-3.5 text-sm",
  } as const;
  const variants = {
    primary: "bg-primary text-primary-ink hover:bg-primary/90",
    secondary: "border border-line-strong bg-surface text-ink hover:bg-surface-2",
    ghost: "text-muted hover:bg-surface-2 hover:text-ink",
    danger: "border border-danger/40 bg-danger-soft text-danger hover:border-danger",
  } as const;
  return `${base} ${sizes[size]} ${variants[variant]}`;
}

export function Button({
  variant = "secondary",
  size = "md",
  busy = false,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize; busy?: boolean }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={rest.disabled || busy}
      aria-busy={busy || undefined}
      className={`${buttonClass(variant, size)} ${className}`}
    >
      {busy && <SpinnerIcon className="animate-spin" />}
      {children}
    </button>
  );
}

/** Mutually exclusive options shown side by side (window, origin, depth). */
export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-md border border-line bg-surface-2 p-0.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={`min-h-8 rounded-[5px] px-2.5 text-[0.8125rem] whitespace-nowrap transition-colors duration-150 ${
              active ? "bg-surface font-medium text-ink shadow-[0_0_0_1px_var(--line-strong)]" : "text-muted hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-muted">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="min-h-10 rounded-md border border-line-strong bg-surface px-2.5 text-sm text-ink"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-2.5">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={description ? `${id}-d` : undefined}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors duration-150 ${
          checked ? "border-primary bg-primary" : "border-line-strong bg-surface-2"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 rounded-full shadow-sm transition-transform duration-150 ${
            checked ? "translate-x-[18px] bg-primary-ink" : "translate-x-[3px] bg-muted"
          }`}
        />
      </button>
      <label htmlFor={id} className="text-sm">
        {label}
        {description && (
          <span id={`${id}-d`} className="block text-xs text-muted">
            {description}
          </span>
        )}
      </label>
    </div>
  );
}

/* ---------------------------------------------------------------- data atoms */

type Tone = "neutral" | "primary" | "ok" | "danger" | "bot";

export function Badge({
  tone = "neutral",
  icon,
  children,
  title,
}: {
  tone?: Tone;
  icon?: ReactNode;
  children: ReactNode;
  title?: string;
}) {
  const tones = {
    neutral: "border-line bg-surface-2 text-muted",
    primary: "border-primary/25 bg-primary-soft text-primary",
    ok: "border-ok/25 bg-ok-soft text-ok",
    danger: "border-danger/30 bg-danger-soft text-danger",
    bot: "border-line-strong bg-bot-soft text-bot",
  } as const;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${tones[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}

export function AddressLink({
  address,
  label,
  full = false,
  className = "",
}: {
  address: string;
  label?: string | null;
  full?: boolean;
  className?: string;
}) {
  return (
    <Link
      href={`/wallets/${address}`}
      title={address}
      className={`rounded-sm text-primary underline-offset-2 hover:underline ${label ? "" : "mono"} ${className}`}
    >
      {label ?? (full ? address : shortAddress(address))}
    </Link>
  );
}

export function CopyButton({ text, label = "Copy address" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard
          ?.writeText(text)
          .then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          })
          .catch(() => undefined);
      }}
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
      className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"
    >
      {copied ? <CheckIcon className="text-ok" /> : <CopyIcon />}
    </button>
  );
}

/** A thin horizontal bar for a 0..1 share. */
export function Meter({ value, tone = "primary", label }: { value: number; tone?: "primary" | "heat" | "muted"; label?: string }) {
  const fill = { primary: "bg-primary", heat: "bg-heat-3", muted: "bg-muted" }[tone];
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className="block h-1.5 w-full overflow-hidden rounded-full bg-surface-2 ring-1 ring-line ring-inset"
    >
      <span className={`block h-full rounded-full ${fill}`} style={{ width: `${clamped * 100}%` }} />
    </span>
  );
}

/* ---------------------------------------------------------------- states */

export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <span aria-hidden="true" className={`block animate-pulse rounded bg-surface-2 ring-1 ring-line ring-inset ${className}`} />;
}

export function SkeletonRows({ rows = 5, className = "" }: { rows?: number; className?: string }) {
  return (
    <div role="status" aria-label="Loading" className={`space-y-2.5 ${className}`}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={`h-5 ${i % 3 === 2 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
  compact = false,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`flex flex-col items-start gap-2 ${compact ? "py-2" : "rounded-lg border border-dashed border-line-strong px-5 py-8 sm:items-center sm:text-center"}`}>
      {icon && <span className="text-muted">{icon}</span>}
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="max-w-prose text-sm leading-relaxed text-muted">{children}</div>}
      {action && <div className="mt-1 flex flex-wrap gap-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-start gap-3 rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
      <AlertIcon className="mt-0.5 shrink-0" />
      <p className="min-w-0 flex-1 basis-48">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 font-medium underline-offset-2 hover:underline">
          <RefreshIcon size={14} />
          Try again
        </button>
      )}
    </div>
  );
}

/**
 * Renders an ``ApiState`` consistently: skeleton while the first load runs,
 * an error with retry, an empty state (also used for a 404), then the content
 * (dimmed while reloading).
 */
export function Async<T>({
  state,
  skeleton,
  isEmpty,
  empty,
  children,
}: {
  state: ApiState<T>;
  skeleton?: ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  // A 404 from a list endpoint means "nothing computed yet", not a failure.
  if (state.status === 404 && empty !== undefined) return <>{empty}</>;
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />;
  if (state.data === undefined) return <>{skeleton ?? <SkeletonRows />}</>;
  if (isEmpty?.(state.data)) return <>{empty}</>;
  return (
    <div aria-busy={state.loading} className={`transition-opacity duration-150 ${state.loading ? "opacity-60" : ""}`}>
      {children(state.data)}
    </div>
  );
}

/* ---------------------------------------------------------------- pagination */

export function Pagination({
  offset,
  limit,
  total,
  noun,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  noun: string;
  onChange: (offset: number) => void;
}) {
  if (total === 0) return null;
  const end = Math.min(offset + limit, total);
  return (
    <nav aria-label={`${noun} pages`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-5">
      <p className="num text-[0.8125rem] text-muted" aria-live="polite">
        {(offset + 1).toLocaleString("en-US")}–{end.toLocaleString("en-US")} of {total.toLocaleString("en-US")} {noun}
      </p>
      {total > limit && (
        <div className="flex gap-2">
          <Button size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
            <ChevronLeft size={14} />
            Previous
          </Button>
          <Button size="sm" disabled={end >= total} onClick={() => onChange(offset + limit)}>
            Next
            <ChevronRight size={14} />
          </Button>
        </div>
      )}
    </nav>
  );
}
