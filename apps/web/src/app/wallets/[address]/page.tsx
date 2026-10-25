import type { Metadata } from "next";

import { shortAddress } from "@/lib/format";

import { WalletView } from "./WalletView";

type Props = { params: Promise<{ address: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { address } = await params;
  return { title: `Wallet ${shortAddress(address.toLowerCase())}` };
}

export default async function WalletPage({ params }: Props) {
  const { address } = await params;
  return <WalletView address={address.toLowerCase()} />;
}
