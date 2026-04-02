import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { Filter, X, Save, Loader2, Maximize2, Zap, User } from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import type { GraphNode as GNode, GraphData } from '../types/api'

const TYPE_COLORS: Record<string, string> = {
  founder: '#e5e7eb', category: '#6b7280',
  belief: '#8b5cf6', story: '#3b82f6', style_rule: '#f59e0b',
  thinking_model: '#10b981', contrast_pair: '#ec4899', vocabulary: '#ef4444',
  viral_brain: '#fbbf24', hook_type: '#f97316', structure_template: '#06b6d4',
  viral_pattern: '#a855f7', engagement_profile: '#22c55e', writing_technique: '#e11d48',
}
const TYPE_BG: Record<string, string> = {
  belief: 'bg-purple-500', story: 'bg-blue-500', style_rule: 'bg-amber-500',
  thinking_model: 'bg-emerald-500', contrast_pair: 'bg-pink-500',
  hook_type: 'bg-orange-500', structure_template: 'bg-cyan-500',
  viral_pattern: 'bg-purple-400', engagement_profile: 'bg-green-500', writing_technique: 'bg-rose-500',
}
const TYPE_SIZES: Record<string, number> = {
  founder: 18, category: 12, belief: 5, story: 5, style_rule: 4,
  thinking_model: 4, contrast_pair: 3, vocabulary: 4,
  viral_brain: 18, hook_type: 6, structure_template: 5,
  viral_pattern: 5, engagement_profile: 6, writing_technique: 5,
}
const FOUNDER_FILTERS = ['belief', 'story', 'style_rule', 'thinking_model', 'contrast_pair']
const VIRAL_FILTERS = ['hook_type', 'structure_template', 'viral_pattern', 'engagement_profile', 'writing_technique']
const INTERNAL_KEYS = new Set(['id', 'type', 'label', 'node_type', 'isHub', 'hasChildren', 'childCount', 'isExpanded', '_raw'])

export default function GraphPage() {
  const active = useFounderStore((s) => s.active)
  const [searchParams, setSearchParams] = useSearchParams()
  const targetNodeId = searchParams.get('node')
  const [graphSource, setGraphSource] = useState<'founder' | 'viral'>('founder')
  const [filter, setFilter] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['founder']))
  const [selectedNode, setSelectedNode] = useState<GNode | null>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const [containerSize, setContainerSize] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth - 40 : 800,
    height: typeof window !== 'undefined' ? window.innerHeight - 140 : 600,
  })
  const containerRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<ForceGraphMethods>(undefined)

  const rootId = graphSource === 'founder' ? 'founder' : 'viral_brain'
  const isHubNode = useCallback((id: string) => id === rootId || id.startsWith('cat_'), [rootId])

  const { data: graphData, isLoading } = useQuery<GraphData>({
    queryKey: [graphSource === 'founder' ? 'graph-nodes' : 'viral-graph-nodes', active, graphSource],
    queryFn: () => apiGet(graphSource === 'founder' ? '/api/graph/nodes' : '/api/viral-graph/nodes'),
  })

  // Reset on source switch
  useEffect(() => {
    setExpanded(new Set([rootId]))
    setFilter(null)
    setSelectedNode(null)
    setHoveredNode(null)
  }, [graphSource, rootId])

  // Resize
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver(([e]) => setContainerSize({ width: e.contentRect.width, height: e.contentRect.height }))
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // Configure forces ONCE per source switch (not on every render)
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    fg.d3Force('charge')?.strength(-150).distanceMax(250)
    fg.d3Force('link')?.distance(50).strength(0.8)
    fg.d3Force('center')?.strength(0.1)
  }, [graphSource])

  // Build maps
  const { childrenOf, allNodesById, allEdges } = useMemo(() => {
    const children: Record<string, string[]> = {}
    const byId: Record<string, GNode> = {}
    const edges: Array<{ source: string; target: string; type: string }> = []
    for (const n of graphData?.nodes || []) byId[n.id] = n
    for (const e of graphData?.edges || []) {
      if (e.type === 'CONTAINS' || e.type === 'HAS_CATEGORY') (children[e.source] ??= []).push(e.target)
      edges.push({ source: e.source, target: e.target, type: e.type })
    }
    return { childrenOf: children, allNodesById: byId, allEdges: edges }
  }, [graphData])

  // Auto-navigate to a specific node from URL ?node=xxx
  useEffect(() => {
    if (!targetNodeId || !graphData) return
    const node = allNodesById[targetNodeId]
    if (!node) return

    // Find parent hub (category node) that CONTAINS this node
    const newExpanded = new Set<string>([rootId])
    for (const edge of graphData.edges) {
      if (edge.target === targetNodeId && (edge.type === 'CONTAINS' || edge.type === 'HAS_CATEGORY')) {
        newExpanded.add(edge.source)
        // Also expand the root so category is visible
        for (const e2 of graphData.edges) {
          if (e2.target === edge.source && (e2.type === 'CONTAINS' || e2.type === 'HAS_CATEGORY')) {
            newExpanded.add(e2.source)
          }
        }
      }
    }
    setExpanded(newExpanded)
    setSelectedNode(node)

    // Clear the URL param so it doesn't re-trigger
    setSearchParams({}, { replace: true })

    // Zoom to fit after expansion
    setTimeout(() => fgRef.current?.zoomToFit(400, 50), 800)
  }, [targetNodeId, graphData, allNodesById, rootId, setSearchParams])

  // Visible IDs
  const visibleIds = useMemo(() => {
    const vis = new Set<string>()
    if (allNodesById[rootId]) vis.add(rootId)
    if (expanded.has(rootId)) for (const c of childrenOf[rootId] || []) vis.add(c)
    for (const hubId of Object.keys(childrenOf)) {
      if (expanded.has(hubId)) {
        for (const c of childrenOf[hubId] || []) {
          const n = allNodesById[c]
          if (!filter || n?.type === filter) vis.add(c)
        }
      }
    }
    return vis
  }, [expanded, childrenOf, allNodesById, filter, rootId])

  // Force graph data
  const graphForceData = useMemo(() => {
    const nodes = Array.from(visibleIds).map((id) => {
      const n = allNodesById[id]
      if (!n) return null
      return {
        id, label: n.label || id, nodeType: n.type || 'unknown',
        isHub: isHubNode(id),
        hasChildren: (childrenOf[id] || []).length > 0,
        childCount: (childrenOf[id] || []).length,
        isExpanded: expanded.has(id),
        _raw: n,
      }
    }).filter(Boolean)
    const links = allEdges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
    return { nodes, links }
  }, [visibleIds, allNodesById, childrenOf, expanded, allEdges, isHubNode])

  // Auto-fit after data changes
  useEffect(() => {
    if (fgRef.current && graphForceData.nodes.length > 0) {
      setTimeout(() => fgRef.current?.zoomToFit(400, 50), 600)
    }
  }, [graphForceData.nodes.length, graphSource])

  // Connected nodes for hover
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

  // Node renderer
  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const { id, label, nodeType, isHub, hasChildren, childCount, isExpanded } = node
    const size = TYPE_SIZES[nodeType] || 4
    const color = TYPE_COLORS[nodeType] || '#6b7280'
    const x = node.x || 0, y = node.y || 0
    const dimmed = hoveredNode && !connectedTo.has(id)
    ctx.globalAlpha = dimmed ? 0.12 : 1

    ctx.beginPath()
    ctx.arc(x, y, size, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()

    if (isHub) {
      ctx.strokeStyle = isExpanded ? '#6366f1' : '#4b5563'
      ctx.lineWidth = isExpanded ? 2 : 1.5
      ctx.stroke()
    }

    if (hasChildren && childCount > 0 && globalScale > 0.3) {
      const bx = x + size * 0.7, by = y - size * 0.7
      ctx.beginPath(); ctx.arc(bx, by, 4, 0, 2 * Math.PI)
      ctx.fillStyle = isExpanded ? '#6366f1' : '#374151'; ctx.fill()
      ctx.fillStyle = '#fff'
      ctx.font = `bold ${Math.max(3, 6 / Math.sqrt(globalScale))}px sans-serif`
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
      ctx.fillText(childCount > 99 ? '99+' : String(childCount), bx, by)
    }

    if (globalScale > 0.4 || isHub) {
      const fs = isHub ? Math.max(4, 10 / globalScale) : Math.max(3, 7 / globalScale)
      ctx.font = `${isHub ? 'bold ' : ''}${fs}px Inter, system-ui, sans-serif`
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      ctx.fillStyle = dimmed ? '#6b708530' : '#d1d5db'
      const maxL = isHub ? 20 : 15
      ctx.fillText(label.length > maxL ? label.slice(0, maxL) + '...' : label, x, y + size + 2)
    }

    if (isHub && hasChildren && globalScale > 0.5) {
      ctx.fillStyle = '#9ca3af'
      ctx.font = `${Math.max(4, 8 / globalScale)}px sans-serif`
      ctx.textAlign = 'center'
      ctx.fillText(isExpanded ? '▼' : '▶', x, y + size + 14)
    }
    ctx.globalAlpha = 1
  }, [hoveredNode, connectedTo])

  // Edge renderer — VISIBLE edges
  const linkCanvasObject = useCallback((link: any, ctx: CanvasRenderingContext2D) => {
    const s = link.source, t = link.target
    if (!s || !t || s.x == null || t.x == null) return
    const isH = link.type === 'CONTAINS' || link.type === 'HAS_CATEGORY'
    const dimmed = hoveredNode && !(connectedTo.has(s.id) && connectedTo.has(t.id))
    ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y)
    ctx.strokeStyle = dimmed ? '#ffffff05' : isH ? '#4b5563' : '#6b728060'
    ctx.lineWidth = isH ? 1.2 : 0.6
    ctx.stroke()
  }, [hoveredNode, connectedTo])

  // Click handler
  const handleNodeClick = useCallback((node: any) => {
    if (isHubNode(node.id) && (childrenOf[node.id] || []).length > 0) {
      setExpanded((prev) => {
        const next = new Set(prev)
        if (next.has(node.id)) {
          next.delete(node.id)
          for (const c of childrenOf[node.id] || []) next.delete(c)
        } else {
          next.add(node.id)
        }
        return next
      })
      setTimeout(() => fgRef.current?.zoomToFit(400, 40), 600)
    } else {
      setSelectedNode(allNodesById[node.id] || null)
    }
  }, [childrenOf, allNodesById, isHubNode])

  if (isLoading) {
    return <div className="flex items-center justify-center py-20"><Loader2 size={24} className="animate-spin text-gray-400" /></div>
  }

  const totalNodes = graphData?.nodes?.length || 0
  const visibleCount = graphForceData.nodes.length
  const filterTypes = graphSource === 'founder' ? FOUNDER_FILTERS : VIRAL_FILTERS

  // Build detail fields for selected node
  const detailFields = selectedNode ? Object.entries(selectedNode)
    .filter(([k, v]) => !INTERNAL_KEYS.has(k) && v != null && v !== '')
    .filter(([k]) => k !== 'node_type')
    .map(([k, v]) => ({ key: k, label: k.replace(/_/g, ' '), value: v }))
    : []

  return (
    <div className="flex h-[calc(100vh-120px)] gap-4">
      <div ref={containerRef} className="relative flex-1 min-h-0 overflow-hidden rounded-xl border border-gray-800 bg-gray-950">
        {/* Toggle + Filters */}
        <div className="absolute left-3 top-3 z-10 flex flex-col gap-2">
          <div className="flex gap-1.5">
            <button onClick={() => setGraphSource('founder')}
              className={clsx('flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors',
                graphSource === 'founder' ? 'bg-indigo-600 text-white' : 'bg-gray-800/80 text-gray-400 hover:text-gray-200 backdrop-blur')}>
              <User size={12} /> Founder Graph
            </button>
            <button onClick={() => setGraphSource('viral')}
              className={clsx('flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors',
                graphSource === 'viral' ? 'bg-amber-600 text-white' : 'bg-gray-800/80 text-gray-400 hover:text-gray-200 backdrop-blur')}>
              <Zap size={12} /> Viral Brain
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <button onClick={() => setFilter(null)}
              className={clsx('flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-colors',
                !filter ? 'bg-indigo-600 text-white' : 'bg-gray-800/80 text-gray-400 hover:text-gray-200 backdrop-blur')}>
              <Filter size={12} /> All
            </button>
            {filterTypes.map((t) => (
              <button key={t} onClick={() => setFilter(filter === t ? null : t)}
                className={clsx('flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors backdrop-blur',
                  filter === t ? 'bg-indigo-600 text-white' : 'bg-gray-800/80 text-gray-400 hover:text-gray-200')}>
                <span className={clsx('h-2 w-2 rounded-full', TYPE_BG[t])} />
                {t.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="absolute right-3 top-3 z-10 flex items-center gap-2">
          <span className="rounded-lg bg-gray-900/80 px-3 py-1.5 text-xs text-gray-400 backdrop-blur">
            {visibleCount}/{totalNodes} nodes
          </span>
          <button onClick={() => fgRef.current?.zoomToFit(400)}
            className="rounded-lg bg-gray-900/80 p-1.5 text-gray-400 backdrop-blur hover:text-gray-200" title="Fit to view">
            <Maximize2 size={14} />
          </button>
        </div>

        {/* Canvas graph — stable ref, no inline force config */}
        <ForceGraph2D
          ref={fgRef as any}
          graphData={graphForceData}
          width={containerSize.width}
          height={containerSize.height}
          backgroundColor="#030712"
          nodeCanvasObject={nodeCanvasObject}
          nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
            ctx.beginPath(); ctx.arc(node.x || 0, node.y || 0, (TYPE_SIZES[node.nodeType] || 4) + 3, 0, 2 * Math.PI)
            ctx.fillStyle = color; ctx.fill()
          }}
          linkCanvasObject={linkCanvasObject}
          onNodeClick={handleNodeClick}
          onNodeHover={(node: any) => setHoveredNode(node?.id || null)}
          cooldownTicks={120}
          d3AlphaDecay={0.05}
          d3VelocityDecay={0.4}
          warmupTicks={30}
          enableNodeDrag
          enableZoomInteraction
          enablePanInteraction
        />
      </div>

      {/* Sidebar: Node Details — generic for ALL node types */}
      {selectedNode && (
        <div className="w-80 space-y-4 overflow-y-auto rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-200">Node Details</h3>
            <button onClick={() => setSelectedNode(null)} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
          </div>

          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full" style={{ backgroundColor: TYPE_COLORS[selectedNode.type] || '#6b7280' }} />
            <span className="text-xs font-medium uppercase tracking-wider text-gray-400">
              {selectedNode.type?.replace(/_/g, ' ')}
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">Label</label>
              <input type="text" defaultValue={selectedNode.label}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none" />
            </div>

            {/* Render ALL non-internal fields dynamically */}
            {detailFields.map(({ key, label, value }) => (
              <div key={key}>
                <label className="mb-1 block text-xs font-medium text-gray-500 capitalize">{label}</label>
                {typeof value === 'number' ? (
                  <input type="number" defaultValue={value} step="any"
                    className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none" />
                ) : typeof value === 'boolean' ? (
                  <span className={clsx('text-sm font-medium', value ? 'text-emerald-400' : 'text-gray-500')}>
                    {value ? 'Yes' : 'No'}
                  </span>
                ) : Array.isArray(value) ? (
                  <div className="flex flex-wrap gap-1">
                    {value.map((v, i) => (
                      <span key={i} className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300">
                        {typeof v === 'object' ? JSON.stringify(v).slice(0, 40) : String(v)}
                      </span>
                    ))}
                  </div>
                ) : typeof value === 'object' ? (
                  <pre className="max-h-24 overflow-y-auto rounded bg-gray-800 p-2 text-xs text-gray-400">
                    {JSON.stringify(value, null, 2)}
                  </pre>
                ) : String(value).length > 80 ? (
                  <textarea defaultValue={String(value)} rows={3}
                    className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none" />
                ) : (
                  <input type="text" defaultValue={String(value)}
                    className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none" />
                )}
              </div>
            ))}

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">ID</label>
              <p className="break-all font-mono text-xs text-gray-600">{selectedNode.id}</p>
            </div>
          </div>

          <button className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500">
            <Save size={14} /> Save Changes
          </button>
        </div>
      )}
    </div>
  )
}
