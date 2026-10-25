import type { Metadata } from "next";
import { Suspense } from "react";

import { SkeletonRows } from "@/components/ui";

import { DiscoverView } from "./DiscoverView";

export const metadata: Metadata = { title: "Discover traders" };

export default function DiscoverPage() {
  return (
    <Suspense fallback={<SkeletonRows rows={10} />}>
      <DiscoverView />
    </Suspense>
  );
}
