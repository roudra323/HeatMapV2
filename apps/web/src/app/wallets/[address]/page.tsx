import { WalletView } from "./WalletView";

export default async function WalletPage({ params }: { params: Promise<{ address: string }> }) {
  const { address } = await params;
  return <WalletView address={address.toLowerCase()} />;
}
