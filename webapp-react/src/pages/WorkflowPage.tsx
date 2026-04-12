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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-gray-400" />
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-120px)] gap-4">
      {/* Canvas */}
      <div className="relative flex-1 rounded-xl border border-gray-800 bg-gray-950">
        {/* Toolbar */}
        <div className="absolute right-3 top-3 z-10 flex gap-2">
          <button
            onClick={handleSave}
            disabled={saveMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-200 transition-colors hover:bg-gray-700 disabled:opacity-50"
          >
            {saveMutation.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Save size={12} />
            )}
            Save
          </button>
          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-black transition-colors hover:bg-white disabled:opacity-50"
          >
            {runMutation.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Play size={12} />
            )}
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
          <Controls className="!bg-gray-900 !border-gray-700 !text-gray-300 [&>button]:!bg-gray-800 [&>button]:!border-gray-700 [&>button]:!text-gray-300" />
        </ReactFlow>
      </div>

      {/* Sidebar */}
      {selectedNode && (
        <div className="w-72 space-y-4 rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-200">Node Config</h3>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-gray-500 hover:text-gray-300"
            >
              <X size={16} />
            </button>
          </div>

          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-400">
                Label
              </label>
              <input
                type="text"
                defaultValue={selectedNode.data.label as string}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 focus:border-white/30 focus:outline-none"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-400">
                Type
              </label>
              <p className="text-sm capitalize text-gray-300">
                {selectedNode.type}
              </p>
            </div>

            {selectedNode.data.prompt !== undefined && (
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">
                  Prompt
                </label>
                <textarea
                  defaultValue={selectedNode.data.prompt as string}
                  rows={4}
                  className="w-full resize-none rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 focus:border-white/30 focus:outline-none"
                />
              </div>
            )}

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-400">
                ID
              </label>
              <p className="text-xs font-mono text-gray-500 break-all">
                {selectedNode.id}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
