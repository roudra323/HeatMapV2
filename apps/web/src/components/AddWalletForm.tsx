"use client";

import Link from "next/link";
import { useId, useState, type FormEvent } from "react";

import { api, type WatchEntry } from "@/lib/api";

import { CheckIcon, PlusIcon } from "./icons";
import { Button } from "./ui";

export function AddWalletForm({ onAdded }: { onAdded?: (entry: WatchEntry) => void }) {
  const id = useId();
  const [address, setAddress] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; text: string; address?: string }>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const value = address.trim();
    if (!/^0x[0-9a-fA-F]{40}$/.test(value)) {
      setStatus({ ok: false, text: "Enter a full address: 0x followed by 40 hex characters." });
      return;
    }
    setBusy(true);
    try {
      const entry = await api.post<WatchEntry>("/v1/watchlist", { address: value, note: note.trim() || null });
      setStatus({ ok: true, text: "Tracked. Its history syncs on the next pipeline run.", address: entry.address });
      setAddress("");
      setNote("");
      onAdded?.(entry);
    } catch (err) {
      setStatus({ ok: false, text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="@container">
      <div className="flex flex-col gap-3 @xl:flex-row @xl:items-end">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <label htmlFor={`${id}-a`} className="text-xs font-medium text-muted">
            Wallet address
          </label>
          <input
            id={`${id}-a`}
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="0x…"
            spellCheck={false}
            autoComplete="off"
            aria-invalid={status && !status.ok ? true : undefined}
            aria-describedby={status ? `${id}-s` : undefined}
            className={`mono min-h-10 rounded-md border bg-surface px-3 text-sm ${status && !status.ok ? "border-danger" : "border-line-strong"}`}
          />
        </div>
        <div className="flex flex-col gap-1 @xl:w-56">
          <label htmlFor={`${id}-n`} className="text-xs font-medium text-muted">
            Note <span className="font-normal">(optional)</span>
          </label>
          <input
            id={`${id}-n`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
            placeholder="e.g. Campaign lead"
            className="min-h-10 rounded-md border border-line-strong bg-surface px-3 text-sm"
          />
        </div>
        <Button type="submit" variant="primary" busy={busy}>
          {!busy && <PlusIcon size={14} />}
          Track wallet
        </Button>
      </div>
      <p id={`${id}-s`} role={status && !status.ok ? "alert" : "status"} className="mt-2 min-h-5 text-sm">
        {status &&
          (status.ok ? (
            <span className="inline-flex items-center gap-1.5 text-ok">
              <CheckIcon size={14} />
              {status.text}{" "}
              {status.address && (
                <Link href={`/wallets/${status.address}`} className="font-medium underline underline-offset-2">
                  Open wallet
                </Link>
              )}
            </span>
          ) : (
            <span className="text-danger">{status.text}</span>
          ))}
      </p>
    </form>
  );
}
