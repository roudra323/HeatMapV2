import type { WatchEntry } from "@/lib/api";
import { originOf } from "@/lib/copy";

import { NetworkIcon, SeedIcon, TrendIcon } from "./icons";
import { Badge } from "./ui";

/** How a wallet entered the watchlist: seed, discovered trader or neighbour. */
export function OriginBadge({ entry }: { entry: Pick<WatchEntry, "origin" | "hop"> }) {
  const origin = originOf(entry.origin);
  const icon =
    entry.origin === "trader" ? (
      <TrendIcon size={12} />
    ) : entry.origin === "neighbour" ? (
      <NetworkIcon size={12} />
    ) : (
      <SeedIcon size={12} />
    );
  return (
    <Badge tone={entry.origin === "trader" ? "primary" : "neutral"} icon={icon} title={origin.summary}>
      {origin.label}
    </Badge>
  );
}
