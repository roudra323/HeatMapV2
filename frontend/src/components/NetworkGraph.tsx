'use client'

import { useEffect, useRef, useState } from 'react'
import { NetworkData } from '@/lib/types'

interface NetworkGraphProps {
  network: NetworkData
  highlightCommunity?: string
  searchAddress?: string
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

export default function NetworkGraph({ network, highlightCommunity, searchAddress }: NetworkGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationFrameRef = useRef<number | null>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const [filteredCounts, setFilteredCounts] = useState({ nodes: 0, edges: 0 })
  const [filteredNodes, setFilteredNodes] = useState(network.nodes)

  // Update filtered nodes when network changes
  useEffect(() => {
    setFilteredNodes(network.nodes)
    setFilteredCounts({ nodes: network.nodes.length, edges: network.edges.length })
  }, [network])

  useEffect(() => {
    if (!canvasRef.current) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Set canvas size
    const width = canvas.width = canvas.offsetWidth
    const height = canvas.height = canvas.offsetHeight

    // Filter nodes based on search address or highlight
    let nodes = network.nodes
    let edges = network.edges

    // If searching for a specific address, show only that wallet and its connections
    if (searchAddress) {
      const searchLower = searchAddress.toLowerCase()
      // Find the searched wallet
      const searchedNode = nodes.find(
        (n) => n.id.toLowerCase().includes(searchLower)
      )
      
      if (searchedNode) {
        // Get all wallets connected to the searched wallet
        const connectedNodeIds = new Set<string>()
        connectedNodeIds.add(searchedNode.id)
        
        // Find all edges connected to the searched wallet
        const connectedEdges = edges.filter((e) => {
          const sourceMatch = e.source.toLowerCase().includes(searchLower)
          const targetMatch = e.target.toLowerCase().includes(searchLower)
          return sourceMatch || targetMatch
        })
        
        // Collect all connected wallet IDs
        connectedEdges.forEach((e) => {
          connectedNodeIds.add(e.source)
          connectedNodeIds.add(e.target)
        })
        
        // Filter nodes to only include searched wallet and its connections
        nodes = nodes.filter((n) => connectedNodeIds.has(n.id))
        // Filter edges to only include edges between filtered nodes
        edges = edges.filter(
          (e) => connectedNodeIds.has(e.source) && connectedNodeIds.has(e.target)
        )
      } else {
        // If searched wallet not found, show empty graph
        nodes = []
        edges = []
      }
    } else if (highlightCommunity) {
      // Original community filtering logic
      const highlightedNodeIds = new Set(
        nodes.filter((n) => n.community === highlightCommunity).map((n) => n.id)
      )
      nodes = nodes.filter((n) => highlightedNodeIds.has(n.id))
      edges = edges.filter(
        (e) => highlightedNodeIds.has(e.source) && highlightedNodeIds.has(e.target)
      )
    }
    
    // Update filtered counts and nodes
    setFilteredCounts({ nodes: nodes.length, edges: edges.length })
    setFilteredNodes(nodes)

    // Find the searched wallet node ID for highlighting
    let searchedNodeId: string | null = null
    if (searchAddress) {
      const searchLower = searchAddress.toLowerCase()
      const found = nodes.find((n) => n.id.toLowerCase().includes(searchLower))
      if (found) {
        searchedNodeId = found.id
      }
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
      isSearched: boolean
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
        isSearched: searchedNodeId === node.id,
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

    // Draw function that can be called repeatedly for animation
    const draw = () => {
      // Clear canvas
      ctx.fillStyle = '#1e293b'
      ctx.fillRect(0, 0, width, height)

      // Draw edges - make them more visible
      edges.forEach((edge) => {
        const source = posMap.get(edge.source)
        const target = posMap.get(edge.target)
        if (!source || !target) return

        // Highlight edges connected to searched node
        const isConnectedToSearched = searchedNodeId && 
          (edge.source === searchedNodeId || edge.target === searchedNodeId)

        if (isConnectedToSearched) {
          // Brighter, thicker edges for searched node connections
          ctx.strokeStyle = '#8b5cf6'
          ctx.lineWidth = 2
          ctx.globalAlpha = 0.6
        } else {
          // Regular edges - more visible than before
          ctx.strokeStyle = '#6b7280'
          ctx.lineWidth = 1
          ctx.globalAlpha = 0.5
        }

        ctx.beginPath()
        ctx.moveTo(source.x, source.y)
        ctx.lineTo(target.x, target.y)
        ctx.stroke()
      })

      // Draw nodes
      ctx.globalAlpha = 1
      const time = Date.now() / 1000
      
      nodePositions.forEach((node) => {
        const color = COMMUNITY_COLORS[node.community] || '#6b7280'
        let radius = Math.min(Math.sqrt(node.transactions) * 0.5 + 3, 15)

        // Special styling for searched node
        if (node.isSearched) {
          // Draw pulsing glow effect for searched node
          const pulse = Math.sin(time * 3) * 0.3 + 0.7 // Pulse between 0.4 and 1.0
          
          // Outer glow
          const glowRadius = radius + 8
          const gradient = ctx.createRadialGradient(
            node.x, node.y, radius,
            node.x, node.y, glowRadius
          )
          gradient.addColorStop(0, `rgba(139, 92, 246, ${0.6 * pulse})`)
          gradient.addColorStop(0.5, `rgba(139, 92, 246, ${0.3 * pulse})`)
          gradient.addColorStop(1, 'rgba(139, 92, 246, 0)')
          
          ctx.fillStyle = gradient
          ctx.beginPath()
          ctx.arc(node.x, node.y, glowRadius, 0, 2 * Math.PI)
          ctx.fill()
          
          // Make searched node larger
          radius = radius * 1.5
        }

        // Node circle
        ctx.fillStyle = color
        ctx.beginPath()
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
        ctx.fill()

        // Node border
        if (node.isSearched) {
          // Thick, bright border for searched node
          ctx.strokeStyle = '#fbbf24' // Gold/yellow color
          ctx.lineWidth = 3
        } else if (node.id === hoveredNode) {
          ctx.strokeStyle = '#ffffff'
          ctx.lineWidth = 2
        } else {
          ctx.strokeStyle = '#ffffff'
          ctx.lineWidth = 0.5
        }
        ctx.stroke()
        
        // Add a star indicator for searched node
        if (node.isSearched) {
          ctx.fillStyle = '#fbbf24'
          ctx.font = 'bold 16px Arial'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText('★', node.x, node.y - radius - 12)
        }
      })
    }

    // Initial draw
    draw()

    // Set up animation loop if there's a searched node
    if (searchedNodeId) {
      const animate = () => {
        draw()
        animationFrameRef.current = requestAnimationFrame(animate)
      }
      animationFrameRef.current = requestAnimationFrame(animate)
    }

    // Handle mouse interaction
    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const mouseY = e.clientY - rect.top

      let found = false
      for (const node of nodePositions) {
        let radius = Math.min(Math.sqrt(node.transactions) * 0.5 + 3, 15)
        // Account for larger radius if it's the searched node
        if (node.isSearched) {
          radius = radius * 1.5
        }
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
      // Cancel animation frame on cleanup
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
        animationFrameRef.current = null
      }
    }
  }, [network, highlightCommunity, searchAddress, hoveredNode])

  const communityStats = filteredNodes.reduce((acc, node) => {
    acc[node.community] = (acc[node.community] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div>
      {/* Filtered Count Display */}
      {(searchAddress || highlightCommunity) && (
        <div className="mb-4 p-3 bg-purple-900/30 rounded-lg border border-purple-500/30">
          <p className="text-sm text-purple-300">
            {searchAddress ? (
              <>Showing connections for searched wallet: <code className="bg-slate-700 px-2 py-1 rounded">{searchAddress}</code></>
            ) : (
              <>Filtered by community: <strong>{highlightCommunity}</strong></>
            )}
            {' • '}
            <span className="text-white font-semibold">{filteredCounts.nodes}</span> nodes •{' '}
            <span className="text-white font-semibold">{filteredCounts.edges}</span> connections
          </p>
        </div>
      )}
      
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
