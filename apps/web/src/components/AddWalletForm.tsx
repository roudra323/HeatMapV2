"use client";

import { useState, type FormEvent } from "react";

import { api, type WatchEntry } from "@/lib/api";

export function AddWalletForm({ onAdded }: { onAdded?: (entry: WatchEntry) => void }) {
  const [address, setAddress] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; text: string }>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const entry = await api.post<WatchEntry>("/v1/watchlist", { address, note: note || null });
      setStatus({ ok: true, text: `Tracking ${entry.address}. It will sync on the next run.` });
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
    <div>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="0x… wallet address"
          required
          pattern="^0x[0-9a-fA-F]{40}$"
          className="mono flex-1 rounded-md border border-line bg-bg px-3 py-2 text-sm"
        />
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="note (optional)"
          className="rounded-md border border-line bg-bg px-3 py-2 text-sm sm:w-48"
        />
        <button
          disabled={busy}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Track wallet
        </button>
      </form>
      {status && (
        <p className={`mt-2 text-sm ${status.ok ? "text-ok" : "text-danger"}`}>{status.text}</p>
      )}
    </div>
  );
}
