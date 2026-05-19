import { useMemo, useRef, useEffect, useState } from 'react'
import { sankey as d3sankey, sankeyLinkHorizontal, type SankeyNode, type SankeyLink } from 'd3-sankey'

interface RawNode { name: string; kind?: string }
interface RawLink { source: number; target: number; value: number }

export interface SankeyFlowProps {
  nodes: RawNode[]
  links: RawLink[]
  height?: number
  /** Optional palette: node.kind → hex */
  palette?: Record<string, string>
}

interface SNode extends SankeyNode<RawNode, RawLink> {
  name: string
  kind?: string
}
interface SLink extends SankeyLink<RawNode, RawLink> {}

const FALLBACK_PALETTE: Record<string, string> = {
  tool: '#fde68a',
  pain: '#fca5a5',
  win: '#86efac',
  default: '#94a3b8',
}

/**
 * Sankey diagram for the "before → after" client journey overview.
 *
 * Input shape matches what `/api/revsure/sankey` returns:
 *   { nodes: [{name, kind}, ...], links: [{source: idx, target: idx, value}, ...] }
 *
 * The `kind` field colors the column (tool / pain / win) and `value` controls
 * the link thickness. Hover surfaces a tooltip with the link total.
 */
export default function SankeyFlow({
  nodes,
  links,
  height = 480,
  palette = FALLBACK_PALETTE,
}: SankeyFlowProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(0)
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null)

  useEffect(() => {
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setWidth(e.contentRect.width)
    })
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  const layout = useMemo(() => {
    if (!width || !nodes.length || !links.length) return null
    try {
      const sankeyGen = d3sankey<RawNode, RawLink>()
        .nodeWidth(14)
        .nodePadding(10)
        .extent([[8, 8], [width - 8, height - 8]])

      // Deep-copy because d3-sankey mutates the input arrays
      const graph = sankeyGen({
        nodes: nodes.map(n => ({ ...n })),
        links: links.map(l => ({ ...l })),
      })
      return graph
    } catch (e) {
      console.warn('sankey layout failed:', e)
      return null
    }
  }, [nodes, links, width, height])

  return (
    <div ref={containerRef} className="relative w-full" style={{ height }}>
      {layout && (
        <svg width={width} height={height} className="text-[var(--text-primary)]">
          <defs>
            {(layout.nodes as SNode[]).map((n, i) => (
              <linearGradient key={`grad-${i}`} id={`sankey-grad-${i}`} x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor={palette[n.kind || 'default'] || palette.default} stopOpacity="0.3" />
                <stop offset="100%" stopColor={palette[n.kind || 'default'] || palette.default} stopOpacity="0.7" />
              </linearGradient>
            ))}
          </defs>

          {/* Links */}
          <g>
            {(layout.links as SLink[]).map((link, i) => (
              <path
                key={`link-${i}`}
                d={sankeyLinkHorizontal()(link as any) || undefined}
                fill="none"
                stroke="rgba(148, 163, 184, 0.35)"
                strokeWidth={Math.max(1, (link.width || 1))}
                onMouseMove={(ev) => {
                  const srcName = (link.source as SNode).name
                  const tgtName = (link.target as SNode).name
                  setHover({
                    x: ev.clientX,
                    y: ev.clientY,
                    text: `${srcName} → ${tgtName}: ${link.value} client${link.value === 1 ? '' : 's'}`,
                  })
                }}
                onMouseLeave={() => setHover(null)}
                style={{ cursor: 'pointer', transition: 'stroke 0.2s' }}
                onMouseEnter={(ev) => {
                  (ev.target as SVGPathElement).setAttribute('stroke', 'rgba(167, 139, 250, 0.55)')
                }}
              />
            ))}
          </g>

          {/* Nodes */}
          <g>
            {(layout.nodes as SNode[]).map((n, i) => (
              <g key={`node-${i}`}>
                <rect
                  x={n.x0}
                  y={n.y0}
                  width={(n.x1 || 0) - (n.x0 || 0)}
                  height={(n.y1 || 0) - (n.y0 || 0)}
                  fill={palette[n.kind || 'default'] || palette.default}
                  stroke="rgba(15, 23, 42, 0.5)"
                  strokeWidth={0.5}
                />
                <text
                  x={(n.x0 || 0) < width / 2 ? (n.x1 || 0) + 6 : (n.x0 || 0) - 6}
                  y={((n.y0 || 0) + (n.y1 || 0)) / 2}
                  dy="0.35em"
                  textAnchor={(n.x0 || 0) < width / 2 ? 'start' : 'end'}
                  fontSize={11}
                  fill="#e2e8f0"
                >
                  {(n.name || '').slice(0, 40)}
                </text>
              </g>
            ))}
          </g>
        </svg>
      )}

      {hover && (
        <div
          className="pointer-events-none fixed z-50 rounded-md border border-[var(--border-3)] bg-[var(--surface-2)] px-2 py-1 text-xs"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          {hover.text}
        </div>
      )}

      {!layout && (
        <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
          Sankey data not available yet — extract + index the transcripts first.
        </div>
      )}
    </div>
  )
}
