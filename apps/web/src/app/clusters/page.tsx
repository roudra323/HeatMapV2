import type { Metadata } from "next";

import { ClustersView } from "./ClustersView";

export const metadata: Metadata = { title: "Clusters" };

export default function ClustersPage() {
  return <ClustersView />;
}
