'use client'

import { Wallet } from '@/lib/types'

interface ExportButtonProps {
  wallets: Wallet[]
  filename: string
  label?: string
  variant?: 'primary' | 'secondary'
}

export default function ExportButton({
  wallets,
  filename,
  label = 'Export',
  variant = 'primary',
}: ExportButtonProps) {
  const exportToCSV = () => {
    if (wallets.length === 0) {
      alert('No wallets to export')
      return
    }

    // CSV headers
    const headers = [
      'address',
      'community',
      'total_transactions',
      'unique_tokens',
      'unique_counterparties',
      'stablecoin_ratio',
      'meme_ratio',
      'defi_ratio',
      'wrapped_ratio',
      'nft_ratio',
    ]

    // Create CSV content
    const csvContent = [
      headers.join(','),
      ...wallets.map((wallet) =>
        headers
          .map((header) => {
            const value = wallet[header as keyof Wallet]
            // Wrap address in quotes, format numbers
            if (header === 'address') return `"${value}"`
            if (header === 'community') return `"${value}"`
            if (typeof value === 'number') return value.toFixed(4)
            return value
          })
          .join(',')
      ),
    ].join('\n')

    // Download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute('download', `${filename}.csv`)
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const exportToJSON = () => {
    if (wallets.length === 0) {
      alert('No wallets to export')
      return
    }

    // Create simplified JSON
    const exportData = {
      exported_at: new Date().toISOString(),
      total_wallets: wallets.length,
      wallets: wallets.map((w) => ({
        address: w.address,
        community: w.community,
        total_transactions: w.total_transactions,
        unique_tokens: w.unique_tokens,
        unique_counterparties: w.unique_counterparties,
        behavior_ratios: {
          stablecoin: w.stablecoin_ratio,
          meme: w.meme_ratio,
          defi: w.defi_ratio,
          wrapped: w.wrapped_ratio,
          nft: w.nft_ratio,
        },
      })),
    }

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute('download', `${filename}.json`)
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const exportAddressesOnly = () => {
    if (wallets.length === 0) {
      alert('No wallets to export')
      return
    }

    const addresses = wallets.map((w) => w.address).join('\n')
    const blob = new Blob([addresses], { type: 'text/plain' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute('download', `${filename}_addresses.txt`)
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const baseClasses =
    'px-4 py-2 rounded-lg font-medium transition-all flex items-center gap-2'
  const variantClasses =
    variant === 'primary'
      ? 'bg-green-600 hover:bg-green-700 text-white'
      : 'bg-slate-700 hover:bg-slate-600 text-gray-200'

  return (
    <div className="relative group">
      <button className={`${baseClasses} ${variantClasses}`}>
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
          />
        </svg>
        {label} ({wallets.length})
      </button>

      {/* Dropdown Menu */}
      <div className="absolute right-0 mt-2 w-48 bg-slate-800 border border-purple-500/30 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-20">
        <button
          onClick={exportToCSV}
          className="w-full text-left px-4 py-2 hover:bg-purple-600/20 text-white text-sm rounded-t-lg"
        >
          📊 Export as CSV
        </button>
        <button
          onClick={exportToJSON}
          className="w-full text-left px-4 py-2 hover:bg-purple-600/20 text-white text-sm"
        >
          📦 Export as JSON
        </button>
        <button
          onClick={exportAddressesOnly}
          className="w-full text-left px-4 py-2 hover:bg-purple-600/20 text-white text-sm rounded-b-lg"
        >
          📋 Addresses Only (TXT)
        </button>
      </div>
    </div>
  )
}
