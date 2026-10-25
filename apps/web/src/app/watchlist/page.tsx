import type { Metadata } from "next";
import { Suspense } from "react";

import { SkeletonRows } from "@/components/ui";

import { WatchlistView } from "./WatchlistView";

export const metadata: Metadata = { title: "Watchlist" };

export default function WatchlistPage() {
  return (
    <Suspense fallback={<SkeletonRows rows={10} />}>
      <WatchlistView />
    </Suspense>
  );
}
