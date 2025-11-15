'use client'

import { useState, useEffect } from 'react'
import { apiClient } from '@/lib/api'
import { VisualizationData, Wallet } from '@/lib/types'
import ScatterPlot from '@/components/ScatterPlot'
import NetworkGraph from '@/components/NetworkGraph'
import CommunityStats from '@/components/CommunityStats'
import FilterControls from '@/components/FilterControls'
import SearchBar from '@/components/SearchBar'
import ExportButton from '@/components/ExportButton'
import WalletDetailModal from '@/components/WalletDetailModal'

export default function Home() {
  const [data, setData] = useState<VisualizationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filter states
  const [selectedCommunity, setSelectedCommunity] = useState<string>('all')
  const [visualizationMethod, setVisualizationMethod] = useState<'pca' | 'tsne'>('tsne')
  const [showNetwork, setShowNetwork] = useState(false)

  // Search and detail states
  const [searchAddress, setSearchAddress] = useState<string>('')
  const [selectedWallet, setSelectedWallet] = useState<Wallet | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const result = await apiClient.getVisualizationData()
      setData(result)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
      console.error('Error loading data:', err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-purple-500 mx-auto mb-4"></div>
          <p className="text-white text-xl">Loading wallet behavior data...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="bg-red-900/50 border border-red-500 rounded-lg p-8 max-w-md">
          <h2 className="text-red-300 text-2xl font-bold mb-4">Error</h2>
          <p className="text-red-200 mb-4">{error}</p>
          <button
            onClick={loadData}
            className="bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded-lg transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!data) return null

  // Filter wallets based on selected community and search
  let filteredWallets = data.wallets

  // Filter by community
  if (selectedCommunity !== 'all') {
    filteredWallets = filteredWallets.filter((w) => w.community === selectedCommunity)
  }

  // Filter by search address
  if (searchAddress) {
    filteredWallets = filteredWallets.filter((w) =>
      w.address.toLowerCase().includes(searchAddress.toLowerCase())
    )
  }

  const handleSearch = (address: string) => {
    setSearchAddress(address)
    // If exact match, open the wallet detail
    const exactMatch = data.wallets.find(
      (w) => w.address.toLowerCase() === address.toLowerCase()
    )
    if (exactMatch) {
      setSelectedWallet(exactMatch)
    }
  }

  const handleClearSearch = () => {
    setSearchAddress('')
  }

  const handleWalletClick = (address: string) => {
    const wallet = data.wallets.find((w) => w.address === address)
    if (wallet) {
      setSelectedWallet(wallet)
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white">
      {/* Header */}
      <header className="border-b border-purple-500/30 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="container mx-auto px-6 py-6">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-600 bg-clip-text text-transparent">
            HeatMap: Wallet Behavior Analytics
          </h1>
          <p className="text-gray-400 mt-2">
            Interactive blockchain wallet behavior analysis for Web3 marketers
          </p>

          {/* Summary Stats */}
          <div className="grid grid-cols-3 gap-4 mt-6">
            <div className="bg-purple-900/30 rounded-lg p-4 border border-purple-500/20">
              <p className="text-purple-300 text-sm">Total Wallets</p>
              <p className="text-3xl font-bold">{data.summary.total_wallets}</p>
            </div>
            <div className="bg-purple-900/30 rounded-lg p-4 border border-purple-500/20">
              <p className="text-purple-300 text-sm">Communities</p>
              <p className="text-3xl font-bold">{data.summary.total_communities}</p>
            </div>
            <div className="bg-purple-900/30 rounded-lg p-4 border border-purple-500/20">
              <p className="text-purple-300 text-sm">PCA Variance</p>
              <p className="text-3xl font-bold">
                {(data.summary.pca_explained_variance * 100).toFixed(1)}%
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="container mx-auto px-6 py-8">
        {/* Search Bar */}
        <div className="mb-6">
          <SearchBar onSearch={handleSearch} onClear={handleClearSearch} />
          {searchAddress && (
            <p className="mt-2 text-sm text-purple-300">
              🔍 Searching for: <code className="bg-slate-700 px-2 py-1 rounded">{searchAddress}</code>
              {filteredWallets.length === 0 && (
                <span className="ml-2 text-red-400">- No matches found</span>
              )}
            </p>
          )}
        </div>

        {/* Filter Controls */}
        <FilterControls
          communities={data.community_stats.map((c) => c.community)}
          selectedCommunity={selectedCommunity}
          onCommunityChange={setSelectedCommunity}
          visualizationMethod={visualizationMethod}
          onMethodChange={setVisualizationMethod}
          showNetwork={showNetwork}
          onShowNetworkChange={setShowNetwork}
        />

        {/* Main Visualization Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
          {/* Scatter Plot - Takes 2 columns */}
          <div className="lg:col-span-2">
            <div className="bg-slate-800/50 rounded-lg border border-purple-500/20 p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-2xl font-bold">
                    Wallet Clustering ({visualizationMethod.toUpperCase()})
                  </h2>
                  <p className="text-gray-400 mt-1 text-sm">
                    {filteredWallets.length} wallets •{' '}
                    {selectedCommunity === 'all' ? 'All communities' : selectedCommunity}
                  </p>
                </div>
                <ExportButton
                  wallets={filteredWallets}
                  filename={`heatmap_${selectedCommunity.toLowerCase().replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}`}
                  label="Export Wallets"
                />
              </div>
              <ScatterPlot
                wallets={filteredWallets}
                method={visualizationMethod}
                highlightCommunity={selectedCommunity === 'all' ? undefined : selectedCommunity}
                onWalletClick={handleWalletClick}
              />
            </div>
          </div>

          {/* Community Stats - 1 column */}
          <div className="lg:col-span-1">
            <CommunityStats
              stats={data.community_stats}
              selectedCommunity={selectedCommunity}
              onSelectCommunity={setSelectedCommunity}
            />
          </div>
        </div>

        {/* Network Graph - Full Width */}
        {showNetwork && data.network && (
          <div className="mt-8">
            <div className="bg-slate-800/50 rounded-lg border border-purple-500/20 p-6">
              <h2 className="text-2xl font-bold mb-4">Wallet Interaction Network</h2>
              <p className="text-gray-400 mb-6 text-sm">
                {data.network.nodes.length} nodes " {data.network.edges.length} connections
              </p>
              <NetworkGraph
                network={data.network}
                highlightCommunity={selectedCommunity === 'all' ? undefined : selectedCommunity}
                searchAddress={searchAddress}
              />
            </div>
          </div>
        )}

        {/* Footer Info */}
        <div className="mt-12 p-6 bg-slate-800/30 rounded-lg border border-purple-500/10">
          <h3 className="text-lg font-semibold mb-3">About This Dashboard</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-gray-400">
            <div>
              <p className="font-semibold text-purple-300 mb-2">Behavior Communities:</p>
              <ul className="list-disc list-inside space-y-1">
                <li>NFT Trader: Wallets with NFT (ERC721) transactions</li>
                <li>Stablecoin User: Primarily uses USDT, USDC, DAI</li>
                <li>Meme Trader: Trades PEPE, SHIB, and other meme coins</li>
                <li>DeFi User: Interacts with DeFi protocols (UNI, AAVE, etc.)</li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-purple-300 mb-2">Visualization Methods:</p>
              <ul className="list-disc list-inside space-y-1">
                <li>PCA: Linear dimensionality reduction for global structure</li>
                <li>t-SNE: Non-linear reduction preserving local relationships</li>
                <li>Network Graph: Shows direct wallet-to-wallet connections</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Wallet Detail Modal */}
      <WalletDetailModal wallet={selectedWallet} onClose={() => setSelectedWallet(null)} />
    </main>
  )
}
