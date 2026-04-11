import { useState, useCallback, useMemo, useRef, useEffect, useLayoutEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { Search, X, Save, Loader2, Maximize2, Zap, User, ChevronRight, Link2, Play, SkipForward } from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import type { GraphNode as GNode, GraphData } from '../types/api'

/* ─── Design tokens ─────────────────────────────────────────────────── */
const PAL: Record<string, { fill: string; glow: string; ring: string; gradient: [string, string] }> = {
  founder:            { fill: '#c7d2fe', glow: '#818cf840', ring: '#6366f1', gradient: ['#a5b4fc', '#6366f1'] },
  category:           { fill: '#94a3b8', glow: '#94a3b830', ring: '#64748b', gradient: ['#cbd5e1', '#64748b'] },
  belief:             { fill: '#c4b5fd', glow: '#a78bfa40', ring: '#8b5cf6', gradient: ['#c4b5fd', '#7c3aed'] },
  story:              { fill: '#93c5fd', glow: '#60a5fa40', ring: '#3b82f6', gradient: ['#93c5fd', '#2563eb'] },
  style_rule:         { fill: '#fde68a', glow: '#fbbf2440', ring: '#f59e0b', gradient: ['#fde68a', '#d97706'] },
  thinking_model:     { fill: '#6ee7b7', glow: '#34d39940', ring: '#10b981', gradient: ['#6ee7b7', '#059669'] },
  contrast_pair:      { fill: '#f9a8d4', glow: '#f472b640', ring: '#ec4899', gradient: ['#f9a8d4', '#db2777'] },
  vocabulary:         { fill: '#fca5a5', glow: '#f8717140', ring: '#ef4444', gradient: ['#fca5a5', '#dc2626'] },
  viral_brain:        { fill: '#fde68a', glow: '#fbbf2450', ring: '#f59e0b', gradient: ['#fde68a', '#d97706'] },
  hook_type:          { fill: '#fdba74', glow: '#fb923c40', ring: '#f97316', gradient: ['#fdba74', '#ea580c'] },
  structure_template: { fill: '#67e8f9', glow: '#22d3ee40', ring: '#06b6d4', gradient: ['#67e8f9', '#0891b2'] },
  viral_pattern:      { fill: '#d8b4fe', glow: '#c084fc40', ring: '#a855f7', gradient: ['#d8b4fe', '#9333ea'] },
  engagement_profile: { fill: '#86efac', glow: '#4ade8040', ring: '#22c55e', gradient: ['#86efac', '#16a34a'] },
  writing_technique:  { fill: '#fda4af', glow: '#fb718540', ring: '#f43f5e', gradient: ['#fda4af', '#e11d48'] },
}

const BASE_R: Record<string, number> = {
  founder: 24, category: 16, belief: 7, story: 7, style_rule: 6,
  thinking_model: 6, contrast_pair: 6, vocabulary: 6,
  viral_brain: 24, hook_type: 8, structure_template: 7,
  viral_pattern: 7, engagement_profile: 8, writing_technique: 7,
}

const EDGE_COL: Record<string, string> = {
  SUPPORTS: '#a78bfa40', BEST_FOR: '#60a5fa40', USES_STYLE: '#fbbf2430',
  CONTRADICTS: '#f8717140', RELATED: '#94a3b825', INFORMS: '#34d39930',
  DEMONSTRATES: '#34d39930', ILLUMINATES: '#f472b630',
  CONTAINS: '#475569', HAS_CATEGORY: '#475569', CONSTRAINS: '#f8717125',
}

const HIGHLIGHT_LINK = '#a78bfacc'
const FOUNDER_FILTERS = ['belief', 'story', 'style_rule', 'thinking_model', 'contrast_pair'] as const
const VIRAL_FILTERS = ['hook_type', 'structure_template', 'viral_pattern', 'engagement_profile', 'writing_technique'] as const
const SKIP_KEYS = new Set(['id', 'type', 'label', 'node_type', 'isHub', 'hasChildren', 'childCount', 'isExpanded', '_raw', 'nodeType'])
const p = (t: string) => PAL[t] || PAL.category

/* ─── Component ─────────────────────────────────────────────────────── */
export default function GraphPage() {
  const active = useFounderStore((s) => s.active)
  const [searchParams, setSearchParams] = useSearchParams()
  const targetNodeId = searchParams.get('node')
  const [graphSource, setGraphSource] = useState<'founder' | 'viral'>('founder')
  const [filter, setFilter] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<string[]>([])
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })
  const [tooltip, setTooltip] = useState<{ x: number; y: number; label: string; group: string } | null>(null)
  const [currentZoom, setCurrentZoom] = useState(1)

  // Animation state
  const [isAnimating, setIsAnimating] = useState(false)
  const [visibleNodeIds, setVisibleNodeIds] = useState<Set<string>>(new Set())
  const [currentWave, setCurrentWave] = useState(-1)

  const containerRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined)
  const animationTimersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  const rootId = graphSource === 'founder' ? 'founder' : 'viral_brain'
  const isHubNode = useCallback((id: string) => id === rootId || id.startsWith('cat_'), [rootId])

  /* ── Data ── */
  const { data: graphData, isLoading } = useQuery({
    queryKey: [graphSource === 'founder' ? 'graph-nodes' : 'viral-graph-nodes', active, graphSource],
    queryFn: () => apiGet<GraphData>(graphSource === 'founder' ? '/api/graph/nodes' : '/api/viral-graph/nodes'),
  })

  /* ── Reset on source switch ── */
  useEffect(() => {
    setFilter(null); setSelectedNode(null); setHoveredNode(null)
    setSearchQuery(''); setSearchResults([])
  }, [graphSource, active])

  /* ── Cleanup animation timers ── */
  useEffect(() => {
    return () => {
      animationTimersRef.current.forEach(clearTimeout)
    }
  }, [])

  /* ── Resize observer ── */
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (rect.width > 0 && rect.height > 0) {
      setContainerSize({ width: rect.width, height: rect.height })
    }
    const obs = new ResizeObserver(([e]) =>
      setContainerSize({ width: e.contentRect.width, height: e.contentRect.height }))
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  /* ── Forces ─ */
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    fg.d3Force('charge')?.strength(-300)
    fg.d3Force('link')?.distance(100)
    fg.d3Force('center')?.strength(0.1)
    fg.d3Force('collision')?.radius((n: any) => (BASE_R[n.nodeType] || 5) * 2.5)
  }, [graphSource, isLoading])

  /* ── Maps ── */
  const { allNodesById, allEdges } = useMemo(() => {
    const byId: Record<string, GNode> = {}
    const edges: Array<{ source: string; target: string; type: string }> = []
    for (const n of graphData?.nodes || []) byId[n.id] = n
    for (const e of graphData?.edges || []) {
      edges.push({ source: e.source, target: e.target, type: e.type })
    }
    return { allNodesById: byId, allEdges: edges }
  }, [graphData])

  /* ── Search ── */
  useEffect(() => {
    if (!searchQuery.trim() || !graphData) { setSearchResults([]); return }
    const q = searchQuery.toLowerCase()
    const hits = graphData.nodes
      .filter((n) =>
        `${n.label || ''} ${n.id} ${(n as any).stance || ''} ${(n as any).summary || ''} ${(n as any).description || ''}`
          .toLowerCase().includes(q))
      .map((n) => n.id)
    setSearchResults(hits)
  }, [searchQuery, graphData])

  /* ── URL nav ── */
  useEffect(() => {
    if (!targetNodeId || !graphData) return
    const node = allNodesById[targetNodeId]
    if (!node) return
    setSelectedNode(node)
    setSearchParams({}, { replace: true })
  }, [targetNodeId, graphData, allNodesById, setSearchParams])

  /* ── Force data ── */
  const graphForceData = useMemo(() => {
    const nodes = (graphData?.nodes || [])
      .filter(n => !filter || n.type === filter || isHubNode(n.id))
      .map((n) => {
        const hub = isHubNode(n.id)
        return {
          id: n.id,
          label: n.label || n.id,
          nodeType: n.type || 'unknown',
          isHub: hub,
          size: BASE_R[n.type] || 5,
          _raw: n,
        }
      })
    const idSet = new Set(nodes.map(n => n.id))
    const links = allEdges.filter(e => idSet.has(e.source) && idSet.has(e.target))
    return { nodes, links }
  }, [graphData, allEdges, filter, isHubNode])

  /* ── Build hierarchy levels (BFS from root) ── */
  const nodeHierarchy = useMemo(() => {
    const levels: Record<number, string[]> = {}
    const visited = new Set<string>()
    const queue: Array<{ id: string; level: number }> = [{ id: rootId, level: 0 }]

    while (queue.length > 0) {
      const { id, level } = queue.shift()!
      if (visited.has(id)) continue
      visited.add(id)

      if (!levels[level]) levels[level] = []
      levels[level].push(id)

      for (const edge of allEdges) {
        const childId = edge.source === id ? edge.target : edge.target === id ? edge.source : null
        if (childId && !visited.has(childId) && graphForceData.nodes.find(n => n.id === childId)) {
          queue.push({ id: childId, level: level + 1 })
        }
      }
    }

    return levels
  }, [graphForceData.nodes, allEdges, rootId])

  /* ── Initial zoom ── */
  useEffect(() => {
    if (fgRef.current && graphForceData.nodes.length > 0 && containerSize.width > 0) {
      setTimeout(() => fgRef.current?.zoomToFit(600, 80), 1200)
    }
  }, [graphSource, graphForceData.nodes.length, containerSize.width])

  /* ── Hover: connected set ── */
  const connectedTo = useMemo(() => {
    if (!hoveredNode) return new Set()
    const s = new Set([hoveredNode])
    for (const l of graphForceData.links) {
      const src = typeof l.source === 'string' ? l.source : (l.source as any).id
      const tgt = typeof l.target === 'string' ? l.target : (l.target as any).id
      if (src === hoveredNode) s.add(tgt)
      if (tgt === hoveredNode) s.add(src)
    }
    return s
  }, [hoveredNode, graphForceData.links])

  /* ── Sidebar connections ── */
  const selectedConnections = useMemo(() => {
    if (!selectedNode) return []
    const conns: Array<{ id: string; label: string; type: string; edgeType: string; direction: 'in' | 'out' }> = []
    for (const e of allEdges) {
      if (e.source === selectedNode.id) {
        const n = allNodesById[e.target]
        if (n) conns.push({ id: n.id, label: n.label || n.id, type: n.type, edgeType: e.type, direction: 'out' })
      }
      if (e.target === selectedNode.id) {
        const n = allNodesById[e.source]
        if (n) conns.push({ id: n.id, label: n.label || n.id, type: n.type, edgeType: e.type, direction: 'in' })
      }
    }
    return conns
  }, [selectedNode, allEdges, allNodesById])

  /* ── Hierarchy Animation ── */
  const triggerHierarchyAnimation = useCallback(() => {
    animationTimersRef.current.forEach(clearTimeout)
    animationTimersRef.current = []

    setIsAnimating(true)
    setVisibleNodeIds(new Set())
    setCurrentWave(-1)

    const levels = Object.keys(nodeHierarchy).map(Number).sort((a, b) => a - b)

    levels.forEach((level, index) => {
      const timer = setTimeout(() => {
        setVisibleNodeIds(prev => {
          const next = new Set(prev)
          nodeHierarchy[level].forEach(id => next.add(id))
          return next
        })
        setCurrentWave(level)

        if (index === levels.length - 1) {
          setTimeout(() => setIsAnimating(false), 300)
        }
      }, index * 400)

      animationTimersRef.current.push(timer)
    })
  }, [nodeHierarchy])

  const skipAnimation = useCallback(() => {
    animationTimersRef.current.forEach(clearTimeout)
    animationTimersRef.current = []
    setIsAnimating(false)
    setVisibleNodeIds(new Set(graphForceData.nodes.map(n => n.id)))
    setCurrentWave(-1)
  }, [graphForceData.nodes])

  /* ── Node canvas renderer ── */
  const nodeCanvas = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const { id, label, nodeType, isHub, size } = node
    const r = size
    const c = p(nodeType)
    const x = node.x ?? 0, y = node.y ?? 0
    const isHit = searchResults.length > 0 && searchResults.includes(id)
    const isSel = selectedNode?.id === id
    const isHovered = hoveredNode === id

    const isNodeVisible = !isAnimating || visibleNodeIds.has(id)
    if (!isNodeVisible) return

    const justAppeared = currentWave >= 0 && visibleNodeIds.has(id)
    const popScale = justAppeared ? 1.3 : 1

    const dim = hoveredNode
      ? !connectedTo.has(id)
      : (searchResults.length > 0 && !isHit)

    ctx.globalAlpha = dim ? 0.06 : 1

    /* Outer glow for important nodes */
    if ((isHub || isSel || isHovered) && !dim) {
      const glowR = r + (isHub ? 10 : 6)
      const grad = ctx.createRadialGradient(x, y, r * 0.4, x, y, glowR + 4)
      grad.addColorStop(0, isSel ? '#6366f150' : isHovered ? '#a78bfa40' : c.glow)
      grad.addColorStop(0.6, isSel ? '#6366f118' : isHovered ? '#a78bfa15' : c.glow.slice(0, 7) + '10')
      grad.addColorStop(1, 'transparent')
      ctx.beginPath()
      ctx.arc(x, y, glowR + 4, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()
    }

    /* Main circle with gradient fill */
    const drawR = (isHovered ? r * 1.25 : r) * popScale
    const nodeGrad = ctx.createRadialGradient(x - drawR * 0.3, y - drawR * 0.3, 0, x, y, drawR)
    nodeGrad.addColorStop(0, c.gradient[0])
    nodeGrad.addColorStop(1, c.gradient[1])

    ctx.beginPath()
    ctx.arc(x, y, drawR, 0, Math.PI * 2)
    ctx.fillStyle = nodeGrad
    ctx.fill()

    /* Ring stroke */
    if (isHub || isSel) {
      ctx.strokeStyle = isSel ? '#818cf8' : c.ring
      ctx.lineWidth = isHub ? 2 : 1.5
      ctx.stroke()
    }

    if (isHovered && !isHub) {
      ctx.strokeStyle = 'rgba(255,255,255,0.8)'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }

    /* Pop-in ring for animation */
    if (justAppeared) {
      ctx.beginPath()
      ctx.arc(x, y, drawR + 5, 0, Math.PI * 2)
      ctx.strokeStyle = c.gradient[0] + '30'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }

    /* Hub inner text */
    if (isHub && r >= 12 && !dim) {
      const fs = Math.min(8.5, Math.max(3.5, 8.5 / globalScale))
      ctx.font = `600 ${fs}px "Outfit", system-ui`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = '#0f0f1a'
      ctx.fillText(label.length > 10 ? label.slice(0, 9) + '\u2026' : label, x, y)
    }

    /* Label below node */
    const shouldShowLabel = (() => {
      if (dim) return false
      if (isSel || isHit || isHovered) return true
      if (isHub) return currentZoom > 0.4
      return currentZoom > 0.8
    })()

    if (shouldShowLabel) {
      const baseFontSize = isHub ? 10.5 : 8.5
      const fs = Math.min(baseFontSize, Math.max(3.5, baseFontSize / globalScale))
      ctx.font = `${isHub ? '600 ' : '400 '}${fs}px "DM Sans", system-ui`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      const maxLen = 22
      const displayLabel = label.length > maxLen ? label.slice(0, maxLen - 1) + '\u2026' : label
      const ly = y + (isHovered ? r * 1.25 : r) * popScale + 4

      /* Text shadow */
      ctx.fillStyle = 'rgba(8,8,13,0.8)'
      ctx.fillText(displayLabel, x + 0.5, ly + 0.5)
      /* Text */
      ctx.fillStyle = isHit ? '#fbbf24' : isHovered ? '#ffffff' : isHub ? '#e2e8f0' : '#9898b0'
      ctx.globalAlpha = dim ? 0 : (isHub ? 1 : 0.75)
      ctx.fillText(displayLabel, x, ly)
    }

    ctx.globalAlpha = 1
  }, [hoveredNode, connectedTo, selectedNode, searchResults, currentZoom, isAnimating, visibleNodeIds, currentWave])

  /* ── Edge renderer with subtle curves ── */
  const linkCanvas = useCallback((link: any, ctx: CanvasRenderingContext2D) => {
    const s = link.source, t = link.target
    if (!s || !t || s.x == null) return

    const srcId = typeof s === 'string' ? s : s.id
    const tgtId = typeof t === 'string' ? t : t.id

    if (isAnimating && (!visibleNodeIds.has(srcId) || !visibleNodeIds.has(tgtId))) {
      return
    }

    const isConnectedToHover = hoveredNode && connectedTo.has(srcId) && connectedTo.has(tgtId)
      && (srcId === hoveredNode || tgtId === hoveredNode)

    if (hoveredNode && !isConnectedToHover) {
      ctx.globalAlpha = 0.02
    }

    /* Subtle quadratic curve */
    const mx = (s.x + t.x) / 2
    const my = (s.y + t.y) / 2
    const dx = t.x - s.x
    const dy = t.y - s.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    const curve = Math.min(dist * 0.08, 12)
    const cpx = mx + (dy / dist) * curve
    const cpy = my - (dx / dist) * curve

    ctx.beginPath()
    ctx.moveTo(s.x, s.y)
    ctx.quadraticCurveTo(cpx, cpy, t.x, t.y)
    ctx.strokeStyle = isConnectedToHover ? HIGHLIGHT_LINK : (EDGE_COL[link.type] || 'rgba(255,255,255,0.06)')
    ctx.lineWidth = isConnectedToHover ? 2.5 : 1
    ctx.stroke()

    ctx.globalAlpha = 1
  }, [hoveredNode, connectedTo, isAnimating, visibleNodeIds])

  /* ── Tooltip ─ */
  const handleNodeHover = useCallback((node: any) => {
    queueMicrotask(() => {
      setHoveredNode(node?.id || null)
      if (node) {
        setTooltip({ x: 0, y: 0, label: node.label, group: node.nodeType })
      } else {
        setTooltip(null)
      }
    })
  }, [])

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!tooltip) return
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    setTooltip(prev => prev ? {
      ...prev,
      x: e.clientX - rect.left + 14,
      y: e.clientY - rect.top - 14,
    } : null)
  }, [tooltip])

  const handleClick = useCallback((node: any) => {
    setSelectedNode(allNodesById[node.id] || null)
  }, [allNodesById])

  const navTo = useCallback((id: string) => {
    const node = allNodesById[id]
    if (!node) return
    setSelectedNode(node)
    const gN = graphForceData.nodes.find((n: any) => n.id === id) as any
    if (gN?.x != null && fgRef.current) {
      fgRef.current.centerAt(gN.x, gN.y, 500)
      fgRef.current.zoom(2.5, 500)
    }
  }, [allNodesById, graphForceData.nodes])

  const handleZoom = useCallback((transform: { k: number }) => {
    queueMicrotask(() => setCurrentZoom(transform.k))
  }, [])

  const visible = graphForceData.nodes.length
  const filters = graphSource === 'founder' ? FOUNDER_FILTERS : VIRAL_FILTERS
  const fields = selectedNode ? Object.entries(selectedNode)
    .filter(([k, v]) => !SKIP_KEYS.has(k) && v != null && v !== '' && k !== 'node_type')
    .map(([k, v]) => ({ key: k, label: k.replace(/_/g, ' '), value: v })) : []

  const hierarchyLevels = Object.keys(nodeHierarchy).map(Number).sort((a, b) => a - b)
  const maxWave = hierarchyLevels.length > 0 ? hierarchyLevels[hierarchyLevels.length - 1] : 0

  return (
    <div className="flex h-full w-full gap-3">
      {/* Main Graph Container */}
      <div
        ref={containerRef}
        className="grain relative flex-1 min-h-0 overflow-hidden rounded-2xl border border-white/[0.04] bg-[#0c0c14]"
        onPointerMove={handlePointerMove}
      >
        {/* Ambient corner glows */}
        <div className="pointer-events-none absolute -top-32 -left-32 h-64 w-64 rounded-full bg-indigo-600/[0.04] blur-[80px]" />
        <div className="pointer-events-none absolute -bottom-32 -right-32 h-64 w-64 rounded-full bg-violet-600/[0.03] blur-[80px]" />

        {/* Controls */}
        <div className="glass-panel-strong absolute top-4 left-4 z-10 rounded-xl p-4 animate-slide-up" style={{ animationDelay: '0.1s' }}>
          <h1 className="m-0 mb-1.5 font-[var(--font-display)] text-[15px] font-semibold text-gray-100 tracking-tight">
            Knowledge Graph
          </h1>
          <div className="mb-3 font-[var(--font-mono)] text-[10px] text-gray-500 tabular-nums tracking-wide">
            {visible} nodes &middot; {graphForceData.links.length} edges
          </div>

          {/* Source toggle */}
          <div className="mb-3 flex rounded-lg bg-gray-950/60 p-[3px] border border-white/[0.04]">
            <button onClick={() => setGraphSource('founder')}
              className={clsx('flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11px] font-medium transition-all duration-200',
                graphSource === 'founder'
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/20'
                  : 'text-gray-500 hover:text-gray-300')}>
              <User size={11} /> Founder
            </button>
            <button onClick={() => setGraphSource('viral')}
              className={clsx('flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11px] font-medium transition-all duration-200',
                graphSource === 'viral'
                  ? 'bg-amber-600 text-white shadow-md shadow-amber-500/20'
                  : 'text-gray-500 hover:text-gray-300')}>
              <Zap size={11} /> Viral
            </button>
          </div>

          {/* Animation Controls */}
          <div className="mb-3 space-y-2">
            {!isAnimating ? (
              <button
                onClick={triggerHierarchyAnimation}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-indigo-500/15 bg-indigo-500/[0.08] px-3 py-1.5 text-[11px] font-medium text-indigo-400 transition-all hover:bg-indigo-500/[0.14] hover:border-indigo-500/25"
              >
                <Play size={11} /> Animate Hierarchy
              </button>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-[var(--font-mono)] text-[10px] text-indigo-400">
                    Wave {currentWave + 1}/{maxWave + 1}
                  </span>
                  <button
                    onClick={skipAnimation}
                    className="flex items-center gap-1 rounded-md bg-white/[0.04] px-2 py-0.5 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
                  >
                    <SkipForward size={9} /> Skip
                  </button>
                </div>
                <div className="h-[3px] rounded-full bg-gray-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-300 ease-out"
                    style={{ width: `${((currentWave + 1) / (maxWave + 1)) * 100}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="flex flex-col gap-1 text-[11px]">
            {filters.map(t => (
              <button key={t} onClick={() => setFilter(filter === t ? null : t)}
                className={clsx('flex items-center gap-2 text-left transition-all duration-150 rounded px-1 py-0.5 -mx-1',
                  filter === t
                    ? 'text-gray-100 bg-white/[0.04]'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.02]')}>
                <span
                  className={clsx('h-[7px] w-[7px] shrink-0 rounded-full transition-transform', filter === t && 'scale-125')}
                  style={{ backgroundColor: p(t).gradient[0], boxShadow: filter === t ? `0 0 6px ${p(t).glow}` : 'none' }}
                />
                {t.replace(/_/g, ' ')}
              </button>
            ))}
            {filter && (
              <button onClick={() => setFilter(null)}
                className="mt-1 text-[10px] text-gray-600 hover:text-gray-400 transition-colors">
                Clear filter
              </button>
            )}
          </div>

          <div className="mt-3 text-[9px] text-gray-600/60 leading-relaxed tracking-wide">
            Scroll to zoom &middot; Drag to move &middot; Hover to highlight
          </div>
        </div>

        {/* Search bar */}
        <div className="absolute top-4 right-4 z-10 flex items-center gap-2 animate-slide-up" style={{ animationDelay: '0.2s' }}>
          <div className="relative group">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-600 group-focus-within:text-indigo-400 transition-colors" />
            <input type="text" placeholder="Search nodes..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
              className="glass-panel w-48 rounded-lg py-1.5 pl-7 pr-8 text-[11px] text-gray-200 placeholder-gray-600 transition-all focus:w-56 focus:border-indigo-500/30 focus:outline-none focus:ring-1 focus:ring-indigo-500/20" />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-300">
                <X size={11} />
              </button>
            )}
          </div>
          {searchResults.length > 0 && (
            <span className="rounded-md bg-amber-500/10 px-2 py-1 font-[var(--font-mono)] text-[10px] font-medium text-amber-400 border border-amber-500/15 animate-fade-in">
              {searchResults.length}
            </span>
          )}
          <button onClick={() => fgRef.current?.zoomToFit(600, 80)}
            className="glass-panel rounded-lg p-1.5 text-gray-600 hover:text-gray-300 transition-colors">
            <Maximize2 size={13} />
          </button>
        </div>

        {/* Tooltip */}
        {tooltip && (
          <div
            className="pointer-events-none absolute z-50 flex items-center gap-2 rounded-lg border border-white/[0.08] bg-gray-950/90 px-3 py-2 text-[11px] text-white backdrop-blur-xl shadow-2xl shadow-black/40 animate-fade-in"
            style={{ left: tooltip.x, top: tooltip.y, opacity: tooltip.label ? 1 : 0 }}
          >
            <span
              className="h-2 w-2 rounded-full shrink-0"
              style={{ backgroundColor: p(tooltip.group).gradient[0] }}
            />
            <div>
              <div className="font-medium leading-tight">{tooltip.label}</div>
              <div className="text-[9px] text-gray-500 mt-0.5">{tooltip.group?.replace(/_/g, ' ')}</div>
            </div>
          </div>
        )}

        {/* Loading overlay */}
        {isLoading && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-[#0c0c14]">
            <div className="relative">
              <div className="h-12 w-12 rounded-full border border-indigo-500/20 animate-breathe" />
              <div className="absolute inset-2 rounded-full border border-indigo-400/30 animate-breathe" style={{ animationDelay: '0.5s' }} />
              <div className="absolute inset-4 rounded-full bg-indigo-500/20 animate-breathe" style={{ animationDelay: '1s' }} />
            </div>
            <span className="font-[var(--font-mono)] text-[10px] text-gray-600 tracking-wider">Loading graph...</span>
          </div>
        )}

        <ForceGraph2D
          ref={fgRef as any}
          graphData={graphForceData}
          width={containerSize.width}
          height={containerSize.height}
          backgroundColor="transparent"
          nodeCanvasObject={nodeCanvas}
          linkCanvasObject={linkCanvas}
          nodePointerAreaPaint={(n: any, c: string, ctx: CanvasRenderingContext2D) => {
            if (isAnimating && !visibleNodeIds.has(n.id)) return
            ctx.beginPath()
            ctx.arc(n.x || 0, n.y || 0, (BASE_R[n.nodeType] || 5) + 4, 0, Math.PI * 2)
            ctx.fillStyle = c
            ctx.fill()
          }}
          onNodeClick={handleClick}
          onNodeHover={handleNodeHover}
          onBackgroundClick={() => { setSelectedNode(null); setHoveredNode(null) }}
          onZoom={handleZoom}
          cooldownTicks={300}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.25}
          warmupTicks={100}
          enableNodeDrag
          enableZoomInteraction
          enablePanInteraction
        />
      </div>

      {/* Sidebar */}
      {selectedNode && (
        <div className="w-80 flex flex-col overflow-hidden rounded-2xl border border-white/[0.04] bg-gray-900/80 backdrop-blur-sm animate-slide-in-right">
          {/* Header with color accent */}
          <div className="relative border-b border-white/[0.04] px-4 py-3">
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-[2px]"
              style={{ background: `linear-gradient(to right, ${p(selectedNode.type).gradient[0]}, ${p(selectedNode.type).gradient[1]})` }}
            />
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span
                  className="h-2.5 w-2.5 rounded-full shadow-sm"
                  style={{
                    backgroundColor: p(selectedNode.type).gradient[0],
                    boxShadow: `0 0 8px ${p(selectedNode.type).glow}`
                  }}
                />
                <span className="font-[var(--font-display)] text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500">
                  {selectedNode.type?.replace(/_/g, ' ')}
                </span>
              </div>
              <button onClick={() => setSelectedNode(null)} className="rounded-md p-1 text-gray-600 hover:bg-white/[0.04] hover:text-gray-400 transition-colors">
                <X size={13} />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3.5">
            {/* Label field */}
            <div className="animate-slide-up" style={{ animationDelay: '0.05s' }}>
              <label className="mb-1.5 block text-[9px] font-semibold uppercase tracking-[0.1em] text-gray-600">Label</label>
              <input type="text" defaultValue={selectedNode.label}
                className="w-full rounded-lg border border-white/[0.06] bg-gray-950/50 px-3 py-2 text-[13px] font-medium text-gray-100 transition-colors focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/15" />
            </div>

            {/* Dynamic fields */}
            {fields.map(({ key, label, value }, idx) => (
              <div key={key} className="animate-slide-up" style={{ animationDelay: `${0.05 + (idx + 1) * 0.03}s` }}>
                <label className="mb-1.5 block text-[9px] font-semibold uppercase tracking-[0.1em] text-gray-600">{label}</label>
                {typeof value === 'number' ? (
                  <input type="number" defaultValue={value} step="any"
                    className="w-full rounded-lg border border-white/[0.06] bg-gray-950/50 px-3 py-2 text-[13px] text-gray-100 transition-colors focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/15" />
                ) : Array.isArray(value) ? (
                  <div className="flex flex-wrap gap-1.5">{value.map((v, i) => (
                    <span key={i} className="rounded-md bg-gray-800/60 px-2 py-0.5 text-[10px] text-gray-300 border border-white/[0.04]">
                      {typeof v === 'object' ? JSON.stringify(v).slice(0, 50) : String(v)}
                    </span>
                  ))}</div>
                ) : typeof value === 'object' ? (
                  <pre className="max-h-24 overflow-y-auto rounded-lg bg-gray-950/50 border border-white/[0.04] p-2.5 text-[10px] text-gray-400 font-[var(--font-mono)]">
                    {JSON.stringify(value, null, 2)}
                  </pre>
                ) : String(value).length > 80 ? (
                  <textarea defaultValue={String(value)} rows={3}
                    className="w-full rounded-lg border border-white/[0.06] bg-gray-950/50 px-3 py-2 text-[13px] text-gray-100 leading-relaxed transition-colors focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/15 resize-none" />
                ) : (
                  <input type="text" defaultValue={String(value)}
                    className="w-full rounded-lg border border-white/[0.06] bg-gray-950/50 px-3 py-2 text-[13px] text-gray-100 transition-colors focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/15" />
                )}
              </div>
            ))}

            {/* Connections */}
            {selectedConnections.length > 0 && (
              <div className="animate-slide-up" style={{ animationDelay: `${0.05 + (fields.length + 1) * 0.03}s` }}>
                <label className="mb-2 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.1em] text-gray-600">
                  <Link2 size={9} /> Connections ({selectedConnections.length})
                </label>
                <div className="space-y-1">{selectedConnections.map((c, i) => (
                  <button key={i} onClick={() => navTo(c.id)}
                    className="flex w-full items-center gap-2 rounded-lg border border-white/[0.03] bg-gray-950/30 px-2.5 py-2 text-left transition-all hover:bg-white/[0.03] hover:border-white/[0.06] group">
                    <span className="h-[6px] w-[6px] shrink-0 rounded-full" style={{ backgroundColor: p(c.type).gradient[0] }} />
                    <div className="flex-1 min-w-0">
                      <span className="block truncate text-[11px] text-gray-400 group-hover:text-gray-200 transition-colors">{c.label}</span>
                      <span className="text-[9px] text-gray-700">{c.direction === 'in' ? '\u2190 ' : '\u2192 '}{c.edgeType.replace(/_/g, ' ').toLowerCase()}</span>
                    </div>
                    <ChevronRight size={10} className="text-gray-800 group-hover:text-gray-600 transition-colors" />
                  </button>
                ))}</div>
              </div>
            )}

            {/* ID */}
            <div>
              <label className="mb-1 block text-[9px] font-semibold uppercase tracking-[0.1em] text-gray-600">ID</label>
              <p className="break-all font-[var(--font-mono)] text-[9px] text-gray-700 select-all leading-relaxed">{selectedNode.id}</p>
            </div>
          </div>

          {/* Save button */}
          <div className="border-t border-white/[0.04] p-3">
            <button className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-indigo-500 px-3 py-2 text-[11px] font-semibold text-white shadow-lg shadow-indigo-500/15 hover:shadow-indigo-500/25 active:scale-[0.98] transition-all">
              <Save size={12} /> Save Changes
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
