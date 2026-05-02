import { useState, useCallback, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Save, Play, Loader2, X } from 'lucide-react'
import { apiGet, apiPost } from '../api/client'
import type { WorkflowConfig } from '../types/api'
import AgentNode from '../components/workflow/AgentNode'
import { Spinner } from '../components/ui'

const customNodeTypes = {
  agent: AgentNode,
  source: AgentNode,
  output: AgentNode,
  topic_source: AgentNode,
  topic_matcher: AgentNode,
  generator: AgentNode,
  voter: AgentNode,
  selector: AgentNode,
  refiner: AgentNode,
  massacre: AgentNode,
  humanizer: AgentNode,
  quality_gate: AgentNode,
  coverage: AgentNode,
  custom_agent: AgentNode,
}

export default function WorkflowPage() {
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)

  const { data: workflow, isLoading } = useQuery<WorkflowConfig>({
    queryKey: ['workflow'],
    queryFn: () => apiGet('/api/workflow'),
  })

  const saveMutation = useMutation({
    mutationFn: (wf: WorkflowConfig) => apiPost('/api/workflow', wf),
  })

  const runMutation = useMutation({
    mutationFn: () => apiPost('/api/workflow/run'),
  })

  const initialNodes: Node[] = useMemo(
    () =>
      workflow?.nodes.map((n) => ({
        id: n.id,
        type: n.type || 'agent',
        position: n.position,
        data: {
          label: n.data.label,
          nodeKind: n.type || 'agent',
          status: 'idle',
          prompt: n.data.prompt,
          config: n.data.config,
        },
      })) ?? [],
    [workflow],
  )

  const initialEdges: Edge[] = useMemo(
    () =>
      workflow?.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        style: { stroke: '#4b5563' },
        animated: true,
      })) ?? [],
    [workflow],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useMemo(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const onNodeClick = useCallback((_: any, node: Node) => {
    setSelectedNode(node)
  }, [])

  const handleSave = () => {
    if (!workflow) return
    const updated: WorkflowConfig = {
      ...workflow,
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.type || 'agent',
        position: n.position,
        data: {
          label: n.data.label as string,
          prompt: n.data.prompt as string | undefined,
          config: n.data.config as Record<string, any> | undefined,
        },
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
      })),
    }
    saveMutation.mutate(updated)
  }

  if (isLoading) return <Spinner fullPage />

  return (
    <div className="flex h-[calc(100vh-120px)] gap-4">
      {/* Canvas */}
      <div className="relative flex-1 rounded-xl border border-[var(--border-1)] bg-[var(--surface-1)]">
        {/* Toolbar */}
        <div className="absolute right-3 top-3 z-10 flex gap-2">
          <button
            onClick={handleSave}
            disabled={saveMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--surface-3)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-4)] disabled:opacity-50"
          >
            {saveMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            Save
          </button>
          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-[12px] font-medium text-black transition-colors hover:bg-white/90 disabled:opacity-50"
          >
            {runMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            Run
          </button>
        </div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={customNodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e1e2a" gap={20} />
          <Controls className="!bg-[var(--surface-2)] !border-[var(--border-1)] [&>button]:!bg-[var(--surface-3)] [&>button]:!border-[var(--border-2)] [&>button]:!text-[var(--text-muted)]" />
        </ReactFlow>
      </div>

      {/* Sidebar */}
      {selectedNode && (
        <div className="w-72 space-y-4 rounded-xl border border-[var(--border-1)] bg-[var(--surface-2)] p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">Node Config</h3>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          <div className="space-y-3">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Label
              </label>
              <input
                type="text"
                defaultValue={selectedNode.data.label as string}
                className="field"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Type
              </label>
              <p className="text-[13px] capitalize text-[var(--text-secondary)]">
                {selectedNode.type}
              </p>
            </div>

            {selectedNode.data.prompt !== undefined && (
              <div>
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                  Prompt
                </label>
                <textarea
                  defaultValue={selectedNode.data.prompt as string}
                  rows={4}
                  className="field resize-none"
                />
              </div>
            )}

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                ID
              </label>
              <p className="break-all font-[var(--font-mono)] text-[11px] text-[var(--text-muted)]">
                {selectedNode.id}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
