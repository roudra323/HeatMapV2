'use client'

import { Wallet } from '@/lib/types'

interface WalletDetailModalProps {
  wallet: Wallet | null
  onClose: () => void
}

export default function WalletDetailModal({ wallet, onClose }: WalletDetailModalProps) {
  if (!wallet) return null

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    alert('Address copied to clipboard!')
  }

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-800 border border-purple-500/30 rounded-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-slate-800 border-b border-purple-500/30 p-6 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-white">Wallet Details</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Address */}
          <div>
            <label className="text-sm text-purple-300 font-semibold">Address</label>
            <div className="mt-1 flex items-center gap-2">
              <code className="flex-1 bg-slate-900 px-4 py-3 rounded-lg text-white font-mono text-sm break-all">
                {wallet.address}
              </code>
              <button
                onClick={() => copyToClipboard(wallet.address)}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-3 rounded-lg transition-colors"
                title="Copy address"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
              </button>
            </div>
          </div>

          {/* Community Badge */}
          <div>
            <label className="text-sm text-purple-300 font-semibold">Community</label>
            <div className="mt-1">
              <span className="inline-block bg-purple-600 text-white px-4 py-2 rounded-lg font-semibold">
                {wallet.community}
              </span>
            </div>
          </div>

          {/* Activity Metrics */}
          <div>
            <label className="text-sm text-purple-300 font-semibold mb-3 block">
              Activity Metrics
            </label>
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <p className="text-gray-400 text-xs mb-1">Transactions</p>
                <p className="text-2xl font-bold text-white">{wallet.total_transactions}</p>
              </div>
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <p className="text-gray-400 text-xs mb-1">Unique Tokens</p>
                <p className="text-2xl font-bold text-white">{wallet.unique_tokens}</p>
              </div>
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <p className="text-gray-400 text-xs mb-1">Counterparties</p>
                <p className="text-2xl font-bold text-white">{wallet.unique_counterparties}</p>
              </div>
            </div>
          </div>

          {/* Behavior Breakdown */}
          <div>
            <label className="text-sm text-purple-300 font-semibold mb-3 block">
              Behavior Breakdown
            </label>
            <div className="space-y-3">
              {[
                { label: 'Stablecoin', ratio: wallet.stablecoin_ratio, color: '#10b981', emoji: '💵' },
                { label: 'Meme', ratio: wallet.meme_ratio, color: '#f59e0b', emoji: '🐸' },
                { label: 'DeFi', ratio: wallet.defi_ratio, color: '#3b82f6', emoji: '⚡' },
                { label: 'NFT', ratio: wallet.nft_ratio, color: '#8b5cf6', emoji: '🖼️' },
                { label: 'Wrapped', ratio: wallet.wrapped_ratio, color: '#ec4899', emoji: '🌉' },
              ].map((item) => (
                <div key={item.label}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-sm text-gray-300">
                      {item.emoji} {item.label}
                    </span>
                    <span className="text-sm font-semibold text-white">
                      {(item.ratio * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-2">
                    <div
                      className="h-2 rounded-full transition-all"
                      style={{
                        width: `${item.ratio * 100}%`,
                        backgroundColor: item.color,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Coordinates (for debugging/advanced users) */}
          <div>
            <label className="text-sm text-purple-300 font-semibold mb-3 block">
              Embedding Coordinates
            </label>
            <div className="grid grid-cols-2 gap-4 text-xs font-mono">
              <div className="bg-slate-900/50 p-3 rounded-lg">
                <p className="text-gray-400 mb-1">PCA</p>
                <p className="text-white">
                  x: {wallet.pca_x.toFixed(3)}, y: {wallet.pca_y.toFixed(3)}
                </p>
              </div>
              <div className="bg-slate-900/50 p-3 rounded-lg">
                <p className="text-gray-400 mb-1">t-SNE</p>
                <p className="text-white">
                  x: {wallet.tsne_x.toFixed(3)}, y: {wallet.tsne_y.toFixed(3)}
                </p>
              </div>
            </div>
          </div>

          {/* External Links */}
          <div className="flex gap-3">
            <a
              href={`https://etherscan.io/address/${wallet.address}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-4 py-3 rounded-lg font-medium text-center transition-colors"
            >
              View on Etherscan →
            </a>
            <a
              href={`https://debank.com/profile/${wallet.address}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-3 rounded-lg font-medium text-center transition-colors"
            >
              View on DeBank →
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
