import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { Search, X, Save, Loader2, Maximize2, Zap, User, ChevronRight, Link2 } from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import type { GraphNode as GNode, GraphData } from '../types/api'

/* ─── Design tokens (ported from D3 HTML color system) ──────────────── */

const PAL: Record<string, { fill: string; glow: string; ring: string }> = {
  founder: { fill: '#e0e7ff', glow: '#818cf830', ring: '#6366f1' },
  category: { fill: '#94a3b8', glow: '#94a3b820', ring: '#475569' },
  belief: { fill: '#a78bfa', glow: '#a78bfa30', ring: '#7c3aed' },
  story: { fill: '#60a5fa', glow: '#60a5fa30', ring: '#2563eb' },
  style_rule: { fill: '#fbbf24', glow: '#fbbf2430', ring: '#d97706' },
  thinking_model: { fill: '#34d399', glow: '#34d39930', ring: '#059669' },
  contrast_pair: { fill: '#f472b6', glow: '#f472b630', ring: '#db2777' },
  vocabulary: { fill: '#f87171', glow: '#f8717130', ring: '#dc2626' },
  viral_brain: { fill: '#fbbf24', glow: '#fbbf2440', ring: '#f59e0b' },
  hook_type: { fill: '#fb923c', glow: '#fb923c30', ring: '#ea580c' },
  structure_template: { fill: '#22d3ee', glow: '#22d3ee30', ring: '#0891b2' },
  viral_pattern: { fill: '#c084fc', glow: '#c084fc30', ring: '#9333ea' },
  engagement_profile: { fill: '#4ade80', glow: '#4ade8030', ring: '#16a34a' },
  writing_technique: { fill: '#fb7185', glow: '#fb718530', ring: '#e11d48' },
}

const BASE_R: Record<string, number> = {
  founder: 22, category: 14, belief: 6, story: 6, style_rule: 5,
  thinking_model: 5, contrast_pair: 5, vocabulary: 5,
  viral_brain: 22, hook_type: 7, structure_template: 6,
  viral_pattern: 6, engagement_profile: 7, writing_technique: 6,
}

const EDGE_COL: Record<string, string> = {
  SUPPORTS: '#a78bfa50', BEST_FOR: '#60a5fa50', USES_STYLE: '#fbbf2440',
  CONTRADICTS: '#f8717150', RELATED: '#94a3b830', INFORMS: '#34d39940',
  DEMONSTRATES: '#34d39940', ILLUMINATES: '#f472b640',
  CONTAINS: '#475569', HAS_CATEGORY: '#475569', CONSTRAINS: '#f8717130',
}

const HIGHLIGHT_LINK = '#9d50bbaa'

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
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 })
  const [tooltip, setTooltip] = useState<{ x: number; y: number; label: string; group: string } | null>(null)
  const [currentZoom, setCurrentZoom] = useState(1)

  const containerRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<ForceGraphMethods>(undefined)
  const rootId = graphSource === 'founder' ? 'founder' : 'viral_brain'
  const isHubNode = useCallback((id: string) => id === rootId || id.startsWith('cat_'), [rootId])

  /* ── Data ── */
  const { data: graphData, isLoading } = useQuery<GraphData>({
    queryKey: [graphSource === 'founder' ? 'graph-nodes' : 'viral-graph-nodes', active, graphSource],
    queryFn: () => apiGet(graphSource === 'founder' ? '/api/graph/nodes' : '/api/viral-graph/nodes'),
  })

  /* ── Reset on source switch ── */
  useEffect(() => {
    setFilter(null); setSelectedNode(null); setHoveredNode(null)
    setSearchQuery(''); setSearchResults([])
  }, [graphSource, active])

  /* ── Resize ── */
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver(([e]) =>
      setContainerSize({ width: e.contentRect.width, height: e.contentRect.height }))
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  /* ── Forces (mirroring D3 HTML simulation) ── */
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    fg.d3Force('charge')?.strength(-300)
    fg.d3Force('link')?.distance(100)
    fg.d3Force('center')?.strength(0.1)
    fg.d3Force('collision')?.radius((n: any) => (BASE_R[n.nodeType] || 5) * 2.5)
  }, [graphSource])

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

  /* ── All-nodes-visible force data (flat graph like D3 HTML) ── */
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

  /* ── Initial zoom ── */
  useEffect(() => {
    if (fgRef.current && graphForceData.nodes.length > 0) {
      setTimeout(() => fgRef.current?.zoomToFit(600, 80), 1200)
    }
  }, [graphSource]) // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Hover: connected set (D3 HTML highlight algorithm) ── */
  const connectedTo = useMemo(() => {
    if (!hoveredNode) return new Set<string>()
    const s = new Set<string>([hoveredNode])
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

  /* ── Node canvas renderer (D3 HTML style) ── */
  const nodeCanvas = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const { id, label, nodeType, isHub, size } = node
    const r = size
    const c = p(nodeType)
    const x = node.x ?? 0, y = node.y ?? 0
    const isHit = searchResults.length > 0 && searchResults.includes(id)
    const isSel = selectedNode?.id === id
    const isHovered = hoveredNode === id

    // D3 HTML dimming: if something is hovered, dim non-connected nodes
    const dim = hoveredNode
      ? !connectedTo.has(id)
      : (searchResults.length > 0 && !isHit)

    ctx.globalAlpha = dim ? 0.08 : 1

    // Glow ring for hubs / hovered / selected
    if ((isHub || isSel || isHovered) && !dim) {
      ctx.beginPath()
      ctx.arc(x, y, r + (isHub ? 8 : 5), 0, Math.PI * 2)
      const grad = ctx.createRadialGradient(x, y, r * 0.3, x, y, r + (isHub ? 10 : 6))
      grad.addColorStop(0, isSel ? '#6366f140' : isHovered ? '#9d50bb40' : c.glow)
      grad.addColorStop(1, 'transparent')
      ctx.fillStyle = grad
      ctx.fill()
    }

    // Main circle
    ctx.beginPath()
    ctx.arc(x, y, isHovered ? r * 1.3 : r, 0, Math.PI * 2)
    ctx.fillStyle = c.fill
    ctx.fill()

    // Ring stroke for hubs or selected
    if (isHub || isSel) {
      ctx.strokeStyle = isSel ? '#6366f1' : c.ring
      ctx.lineWidth = isHub ? 2.5 : 1.5
      ctx.stroke()
    }

    // Hover stroke (like D3 HTML .node:hover circle)
    if (isHovered && !isHub) {
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 2
      ctx.stroke()
    }

    // Inner label for hubs
    if (isHub && r >= 12 && !dim) {
      const fs = Math.min(9, Math.max(4, 9 / globalScale))
      ctx.font = `600 ${fs}px system-ui`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = nodeType === 'founder' ? '#1e1b4b' : '#1e293b'
      ctx.fillText(label.length > 10 ? label.slice(0, 9) + '…' : label, x, y)
    }

    // Zoom-adaptive labels (D3 HTML updateLabelVisibility algorithm)
    const shouldShowLabel = (() => {
      if (dim) return false
      if (isSel || isHit || isHovered) return true
      if (isHub) return currentZoom > 0.4
      return currentZoom > 0.8
    })()

    if (shouldShowLabel) {
      const baseFontSize = isHub ? 11 : 9
      // Keep text stable across zoom like D3 HTML: (10 / k)
      const fs = Math.min(baseFontSize, Math.max(4, baseFontSize / globalScale))
      ctx.font = `${isHub ? '600 ' : '400 '}${fs}px system-ui`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      const maxLen = 22
      const displayLabel = label.length > maxLen ? label.slice(0, maxLen - 1) + '…' : label
      const ly = y + (isHovered ? r * 1.3 : r) + 4

      // Text shadow
      ctx.fillStyle = '#0c0f1a90'
      ctx.fillText(displayLabel, x + 0.5, ly + 0.5)
      // Text
      ctx.fillStyle = isHit ? '#fbbf24' : isHovered ? '#ffffff' : isHub ? '#e2e8f0' : '#aaaaaa'
      ctx.globalAlpha = dim ? 0 : (isHub ? 1 : 0.7)
      ctx.fillText(displayLabel, x, ly)
    }

    ctx.globalAlpha = 1
  }, [hoveredNode, connectedTo, selectedNode, searchResults, currentZoom])

  /* ── Edge renderer (D3 HTML style: highlight connected, dim rest) ── */
  const linkCanvas = useCallback((link: any, ctx: CanvasRenderingContext2D) => {
    const s = link.source, t = link.target
    if (!s || !t || s.x == null) return

    const srcId = typeof s === 'string' ? s : s.id
    const tgtId = typeof t === 'string' ? t : t.id
    const isConnectedToHover = hoveredNode && connectedTo.has(srcId) && connectedTo.has(tgtId)
      && (srcId === hoveredNode || tgtId === hoveredNode)

    // D3 HTML: connected links go full opacity + purple, rest go very dim
    if (hoveredNode && !isConnectedToHover) {
      ctx.globalAlpha = 0.03
    }

    ctx.beginPath()
    ctx.moveTo(s.x, s.y)
    ctx.lineTo(t.x, t.y)
    ctx.strokeStyle = isConnectedToHover ? HIGHLIGHT_LINK : (EDGE_COL[link.type] || 'rgba(255,255,255,0.1)')
    ctx.lineWidth = isConnectedToHover ? 2.5 : 1.5
    ctx.stroke()

    ctx.globalAlpha = 1
  }, [hoveredNode, connectedTo])

  /* ── Tooltip on hover (D3 HTML style) ── */
  const handleNodeHover = useCallback((node: any, prevNode: any) => {
    setHoveredNode(node?.id || null)
    if (node) {
      setTooltip({
        x: 0, y: 0, // we'll position via the container event
        label: node.label,
        group: node.nodeType,
      })
    } else {
      setTooltip(null)
    }
  }, [])

  // Track mouse for tooltip positioning
  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!tooltip) return
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    setTooltip(prev => prev ? {
      ...prev,
      x: e.clientX - rect.left + 12,
      y: e.clientY - rect.top - 12,
    } : null)
  }, [tooltip])

  /* ── Click handler ── */
  const handleClick = useCallback((node: any) => {
    setSelectedNode(allNodesById[node.id] || null)
  }, [allNodesById])

  /* ── Navigate from sidebar ── */
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

  /* ── Track zoom for adaptive labels ── */
  const handleZoom = useCallback((transform: { k: number }) => {
    setCurrentZoom(transform.k)
  }, [])

  if (isLoading) return (
    <div className="flex items-center justify-center py-32">
      <Loader2 size={20} className="animate-spin text-slate-500" />
    </div>
  )

  const total = graphData?.nodes?.length || 0
  const visible = graphForceData.nodes.length
  const filters = graphSource === 'founder' ? FOUNDER_FILTERS : VIRAL_FILTERS
  const fields = selectedNode ? Object.entries(selectedNode)
    .filter(([k, v]) => !SKIP_KEYS.has(k) && v != null && v !== '' && k !== 'node_type')
    .map(([k, v]) => ({ key: k, label: k.replace(/_/g, ' '), value: v })) : []

  return (
    <div className="flex h-[calc(100vh-120px)] gap-3">
      <div
        ref={containerRef}
        className="relative flex-1 min-h-0 overflow-hidden rounded-2xl border border-slate-800/60 bg-[#1a1a1a]"
        onPointerMove={handlePointerMove}
      >

        {/* ── Glass-morphism controls (D3 HTML style) ── */}
        <div className="absolute top-5 left-5 z-10 rounded-xl border border-white/10 bg-black/60 p-4 backdrop-blur-xl">
          <h1 className="m-0 mb-2 text-lg font-medium text-slate-100 tracking-tight">Knowledge Graph</h1>
          <div className="mb-3 text-xs text-slate-400/70 tabular-nums">
            Nodes: {visible} | Connections: {graphForceData.links.length}
          </div>

          {/* Source toggle */}
          <div className="mb-3 flex rounded-lg bg-slate-900/80 p-0.5 border border-slate-800/50">
            <button onClick={() => setGraphSource('founder')}
              className={clsx('flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all',
                graphSource === 'founder' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200')}>
              <User size={11} /> Founder
            </button>
            <button onClick={() => setGraphSource('viral')}
              className={clsx('flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all',
                graphSource === 'viral' ? 'bg-amber-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200')}>
              <Zap size={11} /> Viral
            </button>
          </div>

          {/* Legend */}
          <div className="flex flex-col gap-1.5 text-xs">
            {filters.map(t => (
              <button key={t} onClick={() => setFilter(filter === t ? null : t)}
                className={clsx('flex items-center gap-2 text-left transition-all',
                  filter === t ? 'text-slate-100' : 'text-slate-400/80 hover:text-slate-200')}>
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: p(t).fill }} />
                {t.replace(/_/g, ' ')}
              </button>
            ))}
            {filter && (
              <button onClick={() => setFilter(null)}
                className="mt-1 text-[10px] text-slate-500 hover:text-slate-300 transition-colors">
                ✕ Clear filter
              </button>
            )}
          </div>

          <div className="mt-3 text-[10px] text-slate-600 leading-relaxed">
            Scroll to zoom · Drag to move · Hover to highlight
          </div>
        </div>

        {/* ── Search bar (top right) ── */}
        <div className="absolute top-5 right-5 z-10 flex items-center gap-2">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input type="text" placeholder="Search nodes…" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
              className="w-52 rounded-lg border border-white/10 bg-black/60 py-1.5 pl-8 pr-8 text-xs text-slate-200 placeholder-slate-600 backdrop-blur-xl focus:border-indigo-500/50 focus:outline-none" />
            {searchQuery && <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"><X size={12} /></button>}
          </div>
          {searchResults.length > 0 && (
            <span className="rounded-md bg-amber-500/10 px-2 py-1 text-[10px] font-medium text-amber-400 border border-amber-500/20 backdrop-blur-xl">
              {searchResults.length} found
            </span>
          )}
          <button onClick={() => fgRef.current?.zoomToFit(600, 80)}
            className="rounded-lg bg-black/60 p-1.5 text-slate-500 backdrop-blur-xl border border-white/10 hover:text-slate-300">
            <Maximize2 size={13} />
          </button>
        </div>

        {/* ── Tooltip (D3 HTML floating tooltip) ── */}
        {tooltip && (
          <div
            className="pointer-events-none absolute z-50 rounded-md border border-white/20 bg-black/85 px-3 py-1.5 text-xs text-white backdrop-blur-sm transition-opacity"
            style={{ left: tooltip.x, top: tooltip.y, opacity: tooltip.label ? 1 : 0 }}
          >
            <strong>{tooltip.label}</strong>
            <br />
            <span className="text-slate-400">Group: {tooltip.group?.replace(/_/g, ' ')}</span>
          </div>
        )}

        <ForceGraph2D
          ref={fgRef as any}
          graphData={graphForceData}
          width={containerSize.width}
          height={containerSize.height}
          backgroundColor="transparent"
          nodeCanvasObject={nodeCanvas}
          nodePointerAreaPaint={(n: any, c: string, ctx: CanvasRenderingContext2D) => {
            ctx.beginPath()
            ctx.arc(n.x || 0, n.y || 0, (BASE_R[n.nodeType] || 5) + 4, 0, Math.PI * 2)
            ctx.fillStyle = c
            ctx.fill()
          }}
          linkCanvasObject={linkCanvas}
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

      {/* ── Sidebar ── */}
      {selectedNode && (
        <div className="w-80 flex flex-col overflow-hidden rounded-2xl border border-slate-800/60 bg-[#0f1219]">
          <div className="flex items-center justify-between border-b border-slate-800/40 px-4 py-3">
            <div className="flex items-center gap-2.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: p(selectedNode.type).fill }} />
              <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">{selectedNode.type?.replace(/_/g, ' ')}</span>
            </div>
            <button onClick={() => setSelectedNode(null)} className="rounded-md p-1 text-slate-600 hover:bg-slate-800 hover:text-slate-400"><X size={14} /></button>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
            <div>
              <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-slate-600">Label</label>
              <input type="text" defaultValue={selectedNode.label}
                className="w-full rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500/50 focus:outline-none" />
            </div>
            {fields.map(({ key, label, value }) => (
              <div key={key}>
                <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-slate-600">{label}</label>
                {typeof value === 'number' ? (
                  <input type="number" defaultValue={value} step="any" className="w-full rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500/50 focus:outline-none" />
                ) : Array.isArray(value) ? (
                  <div className="flex flex-wrap gap-1.5">{value.map((v, i) => (
                    <span key={i} className="rounded-md bg-slate-800/60 px-2 py-0.5 text-[11px] text-slate-300 border border-slate-700/30">{typeof v === 'object' ? JSON.stringify(v).slice(0, 50) : String(v)}</span>
                  ))}</div>
                ) : typeof value === 'object' ? (
                  <pre className="max-h-24 overflow-y-auto rounded-lg bg-slate-900/50 border border-slate-800 p-2.5 text-[11px] text-slate-400 font-mono">{JSON.stringify(value, null, 2)}</pre>
                ) : String(value).length > 80 ? (
                  <textarea defaultValue={String(value)} rows={3} className="w-full rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-sm text-slate-100 leading-relaxed focus:border-indigo-500/50 focus:outline-none" />
                ) : (
                  <input type="text" defaultValue={String(value)} className="w-full rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500/50 focus:outline-none" />
                )}
              </div>
            ))}
            {selectedConnections.length > 0 && (
              <div>
                <label className="mb-2 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-slate-600">
                  <Link2 size={10} /> Connections ({selectedConnections.length})
                </label>
                <div className="space-y-1">{selectedConnections.map((c, i) => (
                  <button key={i} onClick={() => navTo(c.id)}
                    className="flex w-full items-center gap-2 rounded-lg border border-slate-800/30 bg-slate-900/30 px-2.5 py-2 text-left transition-colors hover:bg-slate-800/40 group">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: p(c.type).fill }} />
                    <div className="flex-1 min-w-0">
                      <span className="block truncate text-[11px] text-slate-300 group-hover:text-slate-100">{c.label}</span>
                      <span className="text-[9px] text-slate-600">{c.direction === 'in' ? '← ' : '→ '}{c.edgeType.replace(/_/g, ' ').toLowerCase()}</span>
                    </div>
                    <ChevronRight size={10} className="text-slate-700 group-hover:text-slate-500" />
                  </button>
                ))}</div>
              </div>
            )}
            <div>
              <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-slate-600">ID</label>
              <p className="break-all font-mono text-[10px] text-slate-700 select-all">{selectedNode.id}</p>
            </div>
          </div>
          <div className="border-t border-slate-800/40 p-3">
            <button className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500 active:scale-[0.98] shadow-sm shadow-indigo-900/30">
              <Save size={13} /> Save Changes
            </button>
          </div>
        </div>
      )}
    </div>
  )
}