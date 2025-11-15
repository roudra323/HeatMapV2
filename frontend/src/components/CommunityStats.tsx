'use client'

import { CommunityStat } from '@/lib/types'

interface CommunityStatsProps {
  stats: CommunityStat[]
  selectedCommunity: string
  onSelectCommunity: (community: string) => void
}

const COMMUNITY_ICONS: Record<string, string> = {
  'NFT Trader': '🖼️',
  'Stablecoin User': '💵',
  'Meme Trader': '🐸',
  'DeFi User': '⚡',
  'Wrapper/Bridge User': '🌉',
  'High Activity Hub': '🔥',
  'Sender/Distributor': '📤',
  'Receiver/Collector': '📥',
  'Mixed Behavior': '🔄',
  'Active Trader': '📈',
}

export default function CommunityStats({
  stats,
  selectedCommunity,
  onSelectCommunity,
}: CommunityStatsProps) {
  const sortedStats = [...stats].sort((a, b) => b.wallet_count - a.wallet_count)

  return (
    <div className="bg-slate-800/50 rounded-lg border border-purple-500/20 p-6 h-fit">
      <h2 className="text-2xl font-bold mb-4">Community Statistics</h2>

      <div className="space-y-3 max-h-[600px] overflow-y-auto">
        {/* All Communities Option */}
        <button
          onClick={() => onSelectCommunity('all')}
          className={`w-full text-left p-4 rounded-lg transition-all ${
            selectedCommunity === 'all'
              ? 'bg-purple-600 border-2 border-purple-400'
              : 'bg-slate-700/50 border-2 border-transparent hover:border-purple-500/50'
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-lg">🌐 All Communities</span>
            <span className="text-2xl font-bold">
              {stats.reduce((sum, s) => sum + s.wallet_count, 0)}
            </span>
          </div>
        </button>

        {/* Individual Communities */}
        {sortedStats.map((stat) => {
          const isSelected = selectedCommunity === stat.community
          const icon = COMMUNITY_ICONS[stat.community] || '📊'

          // Determine primary behavior
          const behaviors = [
            { name: 'Stablecoin', ratio: stat.avg_stablecoin_ratio, emoji: '💵' },
            { name: 'Meme', ratio: stat.avg_meme_ratio, emoji: '🐸' },
            { name: 'DeFi', ratio: stat.avg_defi_ratio, emoji: '⚡' },
            { name: 'NFT', ratio: stat.avg_nft_ratio, emoji: '🖼️' },
          ].sort((a, b) => b.ratio - a.ratio)

          return (
            <button
              key={stat.community}
              onClick={() => onSelectCommunity(stat.community)}
              className={`w-full text-left p-4 rounded-lg transition-all ${
                isSelected
                  ? 'bg-purple-600 border-2 border-purple-400'
                  : 'bg-slate-700/50 border-2 border-transparent hover:border-purple-500/50'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-sm flex items-center gap-2">
                  <span className="text-xl">{icon}</span>
                  {stat.community}
                </span>
                <span className="text-xl font-bold">{stat.wallet_count}</span>
              </div>

              <div className="text-xs text-gray-400 space-y-1">
                <div className="flex justify-between">
                  <span>Total Transactions:</span>
                  <span className="text-purple-300 font-semibold">
                    {stat.total_txs.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Avg per Wallet:</span>
                  <span className="text-purple-300 font-semibold">
                    {(stat.total_txs / stat.wallet_count).toFixed(1)}
                  </span>
                </div>
              </div>

              {/* Behavior Breakdown */}
              <div className="mt-3 space-y-1">
                {behaviors
                  .filter((b) => b.ratio > 0.05)
                  .map((behavior) => (
                    <div key={behavior.name} className="flex items-center gap-2">
                      <div className="flex-1 bg-slate-900/50 rounded-full h-1.5">
                        <div
                          className="bg-purple-500 h-1.5 rounded-full"
                          style={{ width: `${behavior.ratio * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500">
                        {behavior.emoji} {(behavior.ratio * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
