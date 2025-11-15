import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'HeatMap - Wallet Behavior Analytics',
  description: 'Interactive blockchain wallet behavior analysis for Web3 marketers',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
