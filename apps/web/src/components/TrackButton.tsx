"use client";

import { useState } from "react";

import { api, type WatchEntry } from "@/lib/api";

import { CheckIcon, PlusIcon } from "./icons";
import { Badge, Button } from "./ui";

/**
 * "Track" for a wallet that is not on the watchlist yet; a quiet "Tracked"
 * badge once it is. Errors stay next to the button.
 */
export function TrackButton({
  address,
  tracked,
  onTracked,
  size = "sm",
  variant = "secondary",
}: {
  address: string;
  tracked: boolean;
  onTracked?: (entry: WatchEntry) => void;
  size?: "sm" | "md";
  variant?: "primary" | "secondary";
}) {
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState<string>();

  if (tracked || state === "done") {
    return (
      <span role="status">
        <Badge tone="ok" icon={<CheckIcon size={12} />}>
          Tracked
        </Badge>
      </span>
    );
  }

  async function track() {
    setState("busy");
    setError(undefined);
    try {
      const entry = await api.post<WatchEntry>("/v1/watchlist", { address });
      setState("done");
      onTracked?.(entry);
    } catch (err) {
      setState("idle");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <Button size={size} variant={variant} busy={state === "busy"} onClick={track} aria-label={`Track ${address}`}>
        {state !== "busy" && <PlusIcon size={14} />}
        {state === "busy" ? "Tracking" : "Track"}
      </Button>
      {error && (
        <span role="alert" className="max-w-56 text-right text-xs text-danger">
          {error}
        </span>
      )}
    </span>
  );
}
