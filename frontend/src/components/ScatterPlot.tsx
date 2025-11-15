'use client'

import { useMemo } from 'react'
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ZAxis, Cell } from 'recharts'
import { Wallet } from '@/lib/types'

interface ScatterPlotProps {
  wallets: Wallet[]
  method: 'pca' | 'tsne'
  highlightCommunity?: string
}

const COMMUNITY_COLORS: Record<string, string> = {
  'NFT Trader': '#8b5cf6',
  'Stablecoin User': '#10b981',
  'Meme Trader': '#f59e0b',
  'DeFi User': '#3b82f6',
  'Wrapper/Bridge User': '#ec4899',
  'High Activity Hub': '#ef4444',
  'Sender/Distributor': '#06b6d4',
  'Receiver/Collector': '#6366f1',
  'Mixed Behavior': '#84cc16',
  'Active Trader': '#f97316',
}

export default function ScatterPlot({ wallets, method, highlightCommunity }: ScatterPlotProps) {
  const data = useMemo(() => {
    return wallets.map((wallet) => ({
      x: method === 'pca' ? wallet.pca_x : wallet.tsne_x,
      y: method === 'pca' ? wallet.pca_y : wallet.tsne_y,
      z: wallet.total_transactions,
      address: wallet.address,
      community: wallet.community,
      transactions: wallet.total_transactions,
      color: COMMUNITY_COLORS[wallet.community] || '#6b7280',
      opacity: highlightCommunity && wallet.community !== highlightCommunity ? 0.2 : 1,
    }))
  }, [wallets, method, highlightCommunity])

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload
      return (
        <div className="bg-slate-800 border border-purple-500/50 rounded-lg p-3 shadow-lg">
          <p className="text-white font-semibold text-sm">{point.community}</p>
          <p className="text-gray-400 text-xs font-mono">{point.address.slice(0, 10)}...</p>
          <p className="text-purple-300 text-sm mt-1">
            {point.transactions} transactions
          </p>
        </div>
      )
    }
    return null
  }

  return (
    <div className="h-[500px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart
          margin={{ top: 20, right: 20, bottom: 20, left: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            type="number"
            dataKey="x"
            name={method === 'pca' ? 'PC1' : 't-SNE 1'}
            stroke="#9ca3af"
            tick={{ fill: '#9ca3af' }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={method === 'pca' ? 'PC2' : 't-SNE 2'}
            stroke="#9ca3af"
            tick={{ fill: '#9ca3af' }}
          />
          <ZAxis type="number" dataKey="z" range={[20, 200]} />
          <Tooltip content={<CustomTooltip />} />
          <Scatter
            data={data}
            fill="#8b5cf6"
          >
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.color}
                fillOpacity={entry.opacity}
                stroke={entry.opacity === 1 ? '#ffffff' : 'none'}
                strokeWidth={entry.opacity === 1 ? 1 : 0}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-4 justify-center">
        {Object.entries(COMMUNITY_COLORS).map(([community, color]) => {
          const count = wallets.filter((w) => w.community === community).length
          if (count === 0) return null

          return (
            <div key={community} className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-xs text-gray-400">
                {community} ({count})
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
