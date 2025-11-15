'use client'

import { useEffect, useRef, useState } from 'react'
import { NetworkData } from '@/lib/types'

interface NetworkGraphProps {
  network: NetworkData
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

export default function NetworkGraph({ network, highlightCommunity }: NetworkGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  useEffect(() => {
    if (!canvasRef.current) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Set canvas size
    const width = canvas.width = canvas.offsetWidth
    const height = canvas.height = canvas.offsetHeight

    // Filter nodes based on highlight
    let nodes = network.nodes
    let edges = network.edges

    if (highlightCommunity) {
      const highlightedNodeIds = new Set(
        nodes.filter((n) => n.community === highlightCommunity).map((n) => n.id)
      )
      nodes = nodes.filter((n) => highlightedNodeIds.has(n.id))
      edges = edges.filter(
        (e) => highlightedNodeIds.has(e.source) && highlightedNodeIds.has(e.target)
      )
    }

    // Simple force-directed layout simulation (simplified)
    interface NodePosition {
      id: string
      x: number
      y: number
      vx: number
      vy: number
      community: string
      transactions: number
    }

    const nodePositions: NodePosition[] = nodes.map((node, i) => {
      const angle = (i / nodes.length) * 2 * Math.PI
      const radius = Math.min(width, height) * 0.35
      return {
        id: node.id,
        x: width / 2 + radius * Math.cos(angle),
        y: height / 2 + radius * Math.sin(angle),
        vx: 0,
        vy: 0,
        community: node.community,
        transactions: node.transactions,
      }
    })

    // Create position map
    const posMap = new Map<string, NodePosition>()
    nodePositions.forEach((n) => posMap.set(n.id, n))

    // Simple physics simulation
    const simulate = (iterations: number) => {
      const k = 0.1 // Spring constant
      const repulsion = 100 // Repulsion strength
      const damping = 0.9

      for (let iter = 0; iter < iterations; iter++) {
        // Repulsion between nodes
        for (let i = 0; i < nodePositions.length; i++) {
          for (let j = i + 1; j < nodePositions.length; j++) {
            const a = nodePositions[i]
            const b = nodePositions[j]
            const dx = b.x - a.x
            const dy = b.y - a.y
            const dist = Math.sqrt(dx * dx + dy * dy) || 1
            const force = repulsion / (dist * dist)

            a.vx -= force * (dx / dist)
            a.vy -= force * (dy / dist)
            b.vx += force * (dx / dist)
            b.vy += force * (dy / dist)
          }
        }

        // Attraction along edges
        edges.forEach((edge) => {
          const a = posMap.get(edge.source)
          const b = posMap.get(edge.target)
          if (!a || !b) return

          const dx = b.x - a.x
          const dy = b.y - a.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const force = k * dist

          a.vx += force * (dx / dist)
          a.vy += force * (dy / dist)
          b.vx -= force * (dx / dist)
          b.vy -= force * (dy / dist)
        })

        // Update positions with damping
        nodePositions.forEach((node) => {
          node.vx *= damping
          node.vy *= damping
          node.x += node.vx
          node.y += node.vy

          // Keep nodes in bounds
          node.x = Math.max(50, Math.min(width - 50, node.x))
          node.y = Math.max(50, Math.min(height - 50, node.y))
        })
      }
    }

    // Run simulation
    simulate(50)

    // Clear canvas
    ctx.fillStyle = '#1e293b'
    ctx.fillRect(0, 0, width, height)

    // Draw edges
    ctx.strokeStyle = '#4b5563'
    ctx.lineWidth = 0.5
    edges.forEach((edge) => {
      const source = posMap.get(edge.source)
      const target = posMap.get(edge.target)
      if (!source || !target) return

      ctx.globalAlpha = 0.3
      ctx.beginPath()
      ctx.moveTo(source.x, source.y)
      ctx.lineTo(target.x, target.y)
      ctx.stroke()
    })

    // Draw nodes
    ctx.globalAlpha = 1
    nodePositions.forEach((node) => {
      const color = COMMUNITY_COLORS[node.community] || '#6b7280'
      const radius = Math.min(Math.sqrt(node.transactions) * 0.5 + 3, 15)

      // Node circle
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
      ctx.fill()

      // Node border
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = node.id === hoveredNode ? 2 : 0.5
      ctx.stroke()
    })

    // Handle mouse interaction
    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const mouseY = e.clientY - rect.top

      let found = false
      for (const node of nodePositions) {
        const radius = Math.min(Math.sqrt(node.transactions) * 0.5 + 3, 15)
        const dist = Math.sqrt((mouseX - node.x) ** 2 + (mouseY - node.y) ** 2)
        if (dist < radius) {
          setHoveredNode(node.id)
          found = true
          break
        }
      }
      if (!found) setHoveredNode(null)
    }

    canvas.addEventListener('mousemove', handleMouseMove)

    return () => {
      canvas.removeEventListener('mousemove', handleMouseMove)
    }
  }, [network, highlightCommunity, hoveredNode])

  const communityStats = network.nodes.reduce((acc, node) => {
    acc[node.community] = (acc[node.community] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div>
      <canvas
        ref={canvasRef}
        className="w-full h-[600px] rounded-lg border border-purple-500/20"
      />

      {/* Hovered Node Info */}
      {hoveredNode && (
        <div className="mt-4 p-3 bg-slate-700/50 rounded-lg border border-purple-500/30">
          <p className="text-sm font-mono text-gray-400">{hoveredNode}</p>
        </div>
      )}

      {/* Network Legend */}
      <div className="mt-4 flex flex-wrap gap-3 justify-center">
        {Object.entries(communityStats).map(([community, count]) => {
          const color = COMMUNITY_COLORS[community] || '#6b7280'
          return (
            <div key={community} className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-full border border-white/50"
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
