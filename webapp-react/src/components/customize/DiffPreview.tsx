import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Copy, Check, Wand2, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import type { CustomizationResult } from '../../types/api'
import { apiPost } from '../../api/client'
import { useFounderStore } from '../../store/useFounderStore'

interface Props {
  result: CustomizationResult
}

const TABS = ['Full Post', 'By Section'] as const

export default function DiffPreview({ result }: Props) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Full Post')
  const [copied, setCopied] = useState(false)
  const navigate = useNavigate()

  const cleanReasoning = (text: string) => text.replace(/<reasoning>[\s\S]*?<\/reasoning>/ig, '').trim()
  const [finalPost, setFinalPost] = useState(cleanReasoning(result.customized))
  const [selectedText, setSelectedText] = useState('')
  const [selectionRange, setSelectionRange] = useState<[number, number] | null>(null)
  const [rewriteCommand, setRewriteCommand] = useState('')
  const [isRewriting, setIsRewriting] = useState(false)
  const [selectedVariantIndex, setSelectedVariantIndex] = useState(0)
  const variants = result.all_variants || []
  const hasVariants = variants.length > 1
  const activeFounder = useFounderStore(s => s.active)

  useEffect(() => {
    if (variants[selectedVariantIndex]) {
      setFinalPost(cleanReasoning(variants[selectedVariantIndex].text))
    } else {
      setFinalPost(cleanReasoning(result.customized))
    }
  }, [result, selectedVariantIndex, variants])

  const handleCopy = async () => {
    await navigator.clipboard.writeText(finalPost)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleSelect = (e: any) => {
    const text = e.target.value.substring(e.target.selectionStart, e.target.selectionEnd)
    if (text.trim()) {
      setSelectedText(text)
      setSelectionRange([e.target.selectionStart, e.target.selectionEnd])
    } else {
      setSelectedText('')
      setSelectionRange(null)
    }
  }

  const handleRewriteSection = async () => {
    if (!selectedText || !rewriteCommand.trim() || !selectionRange) return
    setIsRewriting(true)
    try {
      const res = await apiPost<{ post: string }>('/api/generate/section-rewrite', {
        entire_post: finalPost,
        selected_section: selectedText,
        command: rewriteCommand,
        platform: 'linkedin',
        founder_slug: activeFounder
      })
      const newSection = cleanReasoning(res.post)
      const newPost = finalPost.substring(0, selectionRange[0]) + newSection + finalPost.substring(selectionRange[1])
      setFinalPost(newPost)
      setSelectedText('')
      setSelectionRange(null)
      setRewriteCommand('')
    } catch (e: any) {
      console.error(e)
      alert("Failed to rewrite section: " + e.message)
    } finally {
      setIsRewriting(false)
    }
  }

  const sectionKeys = Object.keys(result.sections)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-gray-300">Result</h4>
        {hasVariants && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Variant:</span>
            <div className="flex gap-1">
              {variants.map((v, i) => (
                <button
                  key={v.id || i}
                  onClick={() => setSelectedVariantIndex(i)}
                  className={clsx(
                    'flex h-6 w-6 items-center justify-center rounded text-xs font-medium transition-colors',
                    selectedVariantIndex === i
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                  )}
                  title={v.strategy || v.engine_name}
                >
                  {i + 1}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {hasVariants && (
        <div className="text-xs font-medium text-indigo-400 italic">
          Strategy: {variants[selectedVariantIndex].strategy || variants[selectedVariantIndex].engine_name}
        </div>
      )}

      {/* Topic & context info */}
      {result.topic && (
        <div className="flex flex-wrap gap-2 text-xs text-gray-500">
          <span className="rounded bg-gray-800 px-2 py-0.5">
            Topic: {result.topic}
          </span>
          {result.founder_context?.beliefs_count != null && (
            <span className="rounded bg-gray-800 px-2 py-0.5">
              Beliefs: {result.founder_context.beliefs_count}
            </span>
          )}
          {result.founder_context?.style_rules_count != null && (
            <span className="rounded bg-gray-800 px-2 py-0.5">
              Style rules: {result.founder_context.style_rules_count}
            </span>
          )}
          {result.quality && (
            <span className={clsx(
              'rounded px-2 py-0.5',
              result.quality.passed ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
            )}>
              Quality: {result.quality.score}%
            </span>
          )}
        </div>
      )}

      {/* Traceability — which graph nodes influenced this output */}
      {result.traceability && (
        <details className="rounded-lg border border-gray-800 bg-gray-900/50">
          <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-amber-400 hover:text-amber-300">
            Graph Traceability — {(result.traceability.belief_nodes?.length || 0)} beliefs, {(result.traceability.story_nodes?.length || 0)} stories, {(result.traceability.style_rule_nodes?.length || 0)} style rules
          </summary>
          <div className="space-y-2 px-3 pb-3">
            {result.traceability.belief_nodes?.length > 0 && (
              <div>
                <span className="text-xs font-semibold text-indigo-400">Beliefs Used:</span>
                <ul className="mt-1 space-y-0.5">
                  {result.traceability.belief_nodes.map((b) => (
                    <li key={b.node_id} className="text-xs text-gray-400">
                      <button
                        onClick={() => navigate(`/graph?node=${b.node_id}`)}
                        className="text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
                        title="View in graph"
                      >
                        [{b.node_id}]
                      </button>{' '}
                      {b.topic}: {b.stance}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result.traceability.story_nodes?.length > 0 && (
              <div>
                <span className="text-xs font-semibold text-green-400">Stories Used:</span>
                <ul className="mt-1 space-y-0.5">
                  {result.traceability.story_nodes.map((s) => (
                    <li key={s.node_id} className="text-xs text-gray-400">
                      <button
                        onClick={() => navigate(`/graph?node=${s.node_id}`)}
                        className="text-green-400 hover:text-green-300 hover:underline cursor-pointer"
                        title="View in graph"
                      >
                        [{s.node_id}]
                      </button>{' '}
                      {s.title}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result.traceability.style_rule_nodes?.length > 0 && (
              <div>
                <span className="text-xs font-semibold text-purple-400">Style Rules Used:</span>
                <ul className="mt-1 space-y-0.5">
                  {result.traceability.style_rule_nodes.map((r) => (
                    <li key={r.node_id} className="text-xs text-gray-400">
                      <button
                        onClick={() => navigate(`/graph?node=${r.node_id}`)}
                        className="text-purple-400 hover:text-purple-300 hover:underline cursor-pointer"
                        title="View in graph"
                      >
                        [{r.node_id}]
                      </button>{' '}
                      <span className="text-gray-500">[{r.rule_type}]</span> {r.description}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="text-xs text-gray-500">
              Vocabulary: {result.traceability.vocabulary_phrases_used} phrases used, {result.traceability.vocabulary_phrases_never} banned
            </div>
          </div>
        </details>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'border-b-2 px-3 py-1.5 text-sm font-medium transition-colors',
              tab === t
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-300',
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'Full Post' && (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-indigo-400">
              Customized Post
            </span>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <textarea
            readOnly
            value={finalPost}
            onSelect={handleSelect}
            rows={10}
            className="w-full resize-none rounded-lg border border-gray-700 bg-gray-800 p-4 text-sm leading-relaxed text-gray-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />

          {/* Inline Section Rewrite */}
          {selectedText && (
            <div className="mt-2 rounded-lg border border-indigo-800 bg-indigo-950/30 p-4 animate-in fade-in slide-in-from-top-2">
              <div className="text-xs text-indigo-400 mb-2 font-medium">
                <Wand2 size={12} className="inline mr-1" />
                Rewrite selected section
              </div>
              <p className="mb-3 border-l-2 border-indigo-500 pl-3 text-sm italic text-gray-300">
                "{selectedText.length > 100 ? selectedText.substring(0, 100) + '...' : selectedText}"
              </p>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={rewriteCommand}
                  onChange={e => setRewriteCommand(e.target.value)}
                  placeholder="e.g. Make this sound punchier, use shorter sentences..."
                  className="w-full rounded border border-indigo-500/30 bg-indigo-950/50 px-3 py-2 text-sm text-indigo-100 placeholder:text-indigo-400/50 focus:border-indigo-500 focus:outline-none"
                  onKeyDown={e => e.key === 'Enter' && handleRewriteSection()}
                />
                <button
                  onClick={handleRewriteSection}
                  disabled={isRewriting || !rewriteCommand.trim()}
                  className="shrink-0 rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
                  title="Apply rewrite command to selection"
                >
                  {isRewriting ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'By Section' && (
        <div className="space-y-3">
          {sectionKeys.map((key) => {
            const section = result.sections[key]
            return (
              <div
                key={key}
                className="rounded-lg border border-gray-800 bg-gray-900 p-4"
              >
                <span className="mb-2 block text-xs font-semibold capitalize text-gray-400">
                  {key}
                </span>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <span className="mb-1 block text-xs text-gray-500">
                      Original
                    </span>
                    <p className="whitespace-pre-wrap text-sm text-gray-400">
                      {section.original}
                    </p>
                  </div>
                  <div>
                    <span className="mb-1 block text-xs text-indigo-400">
                      Customized
                    </span>
                    <p className="whitespace-pre-wrap text-sm text-gray-200">
                      {section.customized}
                    </p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
