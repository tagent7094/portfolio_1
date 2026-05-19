import { useRef, useEffect, useState, useMemo } from 'react'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'

export interface FGNode {
  id: string
  label?: string
  node_type?: string
  [k: string]: any
}

export interface FGLink {
  source: string | FGNode
  target: string | FGNode
  edge_type?: string
  [k: string]: any
}

export interface FGProps {
  nodes: FGNode[]
  links: FGLink[]
  height?: number
  /** Optional palette: node_type → hex color */
  palette?: Record<string, string>
  /** Click handler for a node (used to open detail panes) */
  onNodeClick?: (node: FGNode) => void
  /** Default node radius (overridden per-type via `radii` map). */
  defaultRadius?: number
  radii?: Record<string, number>
  /** Filter to highlight: nodes matching get full opacity, others fade. */
  highlightTypes?: string[]
}

const FALLBACK_PALETTE: Record<string, string> = {
  Client: '#a5b4fc',
  Pain: '#fca5a5',
  ToolFrom: '#fde68a',
  Tussle: '#f9a8d4',
  Contrarian: '#d8b4fe',
  RevSureProblem: '#fdba74',
  Win: '#86efac',
  BestAspect: '#6ee7b7',
  Quote: '#94a3b8',
}

const FALLBACK_RADII: Record<string, number> = {
  Client: 14,
  Quote: 3,
  default: 6,
}

/**
 * Lightweight, generic force-directed graph viz built on react-force-graph-2d.
 *
 * Usage:
 *   <ForceGraph nodes={data.nodes} links={data.links} onNodeClick={...} />
 *
 * Each node should have at minimum `{ id, label, node_type }`. Links use the
 * standard `{source, target}` shape that react-force-graph expects.
 */
export default function ForceGraph({
  nodes,
  links,
  height = 600,
  palette = FALLBACK_PALETTE,
  onNodeClick,
  defaultRadius,
  radii = FALLBACK_RADII,
  highlightTypes,
}: FGProps) {
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setWidth(e.contentRect.width)
    })
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  // Defensive: nodes/links may be undefined or non-array if a malformed
  // response from /api/revsure/graph reached this component. The
  // react-force-graph-2d library would otherwise throw on .length access.
  const graphData = useMemo(() => ({
    nodes: Array.isArray(nodes) ? nodes : [],
    links: Array.isArray(links) ? links : [],
  }), [nodes, links])
  const highlightSet = useMemo(() => new Set(highlightTypes || []), [highlightTypes])

  return (
    <div ref={containerRef} className="w-full" style={{ height }}>
      {width > 0 && (
        <ForceGraph2D
          ref={fgRef as any}
          graphData={graphData}
          width={width}
          height={height}
          backgroundColor="transparent"
          nodeRelSize={4}
          linkColor={() => 'rgba(148, 163, 184, 0.18)'}
          linkWidth={0.7}
          linkDirectionalParticles={0}
          cooldownTicks={120}
          onNodeClick={(node: any) => {
            if (onNodeClick) onNodeClick(node as FGNode)
          }}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, scale: number) => {
            const t = node.node_type || 'default'
            const r = radii[t] ?? defaultRadius ?? radii.default ?? 6
            const fill = palette[t] || '#94a3b8'
            const faded = highlightSet.size > 0 && !highlightSet.has(t)
            ctx.globalAlpha = faded ? 0.25 : 1
            ctx.beginPath()
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false)
            ctx.fillStyle = fill
            ctx.fill()
            ctx.lineWidth = 0.8
            ctx.strokeStyle = 'rgba(15, 23, 42, 0.5)'
            ctx.stroke()
            // Labels on bigger nodes only
            if (r >= 10 && scale > 0.6) {
              const label = (node.label || node.id || '').slice(0, 28)
              ctx.font = `${Math.max(10, 11 / scale * 0.8)}px ui-sans-serif, system-ui`
              ctx.fillStyle = '#e2e8f0'
              ctx.textAlign = 'center'
              ctx.textBaseline = 'middle'
              ctx.fillText(label, node.x, node.y + r + 8)
            }
            ctx.globalAlpha = 1
          }}
          nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
            const t = node.node_type || 'default'
            const r = (radii[t] ?? defaultRadius ?? radii.default ?? 6) + 2
            ctx.fillStyle = color
            ctx.beginPath()
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false)
            ctx.fill()
          }}
        />
      )}
    </div>
  )
}
