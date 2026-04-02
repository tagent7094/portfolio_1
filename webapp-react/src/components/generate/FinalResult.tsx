import { useState } from 'react'
import { Copy, Check, ShieldCheck, ShieldAlert, RotateCcw, Loader2, Wand2 } from 'lucide-react'
import clsx from 'clsx'
import type { GenerationResult } from '../../types/api'
import { apiPost } from '../../api/client'
import { useFounderStore } from '../../store/useFounderStore'

interface Props {
  result: GenerationResult
}

export default function FinalResult({ result }: Props) {
  const [copied, setCopied] = useState(false)
  const cleanReasoning = (text: string) => text.replace(/<reasoning>[\s\S]*?<\/reasoning>/ig, '').trim()
  const [finalPost, setFinalPost] = useState(cleanReasoning(result.post))

  // Entire post regenerate state
  const [feedback, setFeedback] = useState('')
  const [showFeedback, setShowFeedback] = useState(false)
  const [isRegenerating, setIsRegenerating] = useState(false)

  // Section rewrite state
  const [selectedText, setSelectedText] = useState('')
  const [selectionRange, setSelectionRange] = useState<[number, number] | null>(null)
  const [rewriteCommand, setRewriteCommand] = useState('')
  const [isRewriting, setIsRewriting] = useState(false)

  const activeFounder = useFounderStore(s => s.active)

  const { quality, influence } = result

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
      const newPost = cleanReasoning(res.post).substring(0, selectionRange[0]) + newSection + finalPost.substring(selectionRange[1])
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

  const handleRegenerate = async () => {
    if (!feedback.trim()) return
    setIsRegenerating(true)
    try {
      const res = await apiPost<{ post: string }>('/api/generate/regenerate-with-context', {
        previous_post: finalPost,
        feedback: feedback,
        platform: 'linkedin',
        creativity: 0.5,
        founder_slug: activeFounder
      })
      setFinalPost(res.post)
      setShowFeedback(false)
      setFeedback('')
    } catch (e: any) {
      console.error(e)
      alert("Failed to regenerate: " + e.message)
    } finally {
      setIsRegenerating(false)
    }
  }

  const scores = [
    { label: 'Overall', value: influence?.overall ?? 0 },
    { label: 'Belief', value: influence?.belief_alignment?.score ?? 0 },
    { label: 'Story', value: influence?.story_influence?.score ?? 0 },
    { label: 'Style', value: influence?.style_adherence?.score ?? 0 },
  ]

  return (
    <div className="space-y-4 rounded-xl border border-gray-800 bg-gray-900 p-6">
      {/* Quality badge */}
      <div className="flex items-center gap-3">
        <span
          className={clsx(
            'flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold',
            quality.passed
              ? 'bg-green-600/20 text-green-400'
              : 'bg-red-600/20 text-red-400',
          )}
        >
          {quality.passed ? (
            <ShieldCheck size={16} />
          ) : (
            <ShieldAlert size={16} />
          )}
          {quality.passed ? 'Quality Pass' : 'Quality Fail'} ({quality.score.toFixed(1)})
        </span>
      </div>

      {/* Post */}
      <div className="relative">
        <textarea
          readOnly
          value={finalPost}
          onSelect={handleSelect}
          rows={6}
          className="w-full resize-none rounded-lg border border-gray-700 bg-gray-800 p-4 text-sm leading-relaxed text-gray-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <button
          onClick={handleCopy}
          className="absolute right-3 top-3 rounded-md bg-gray-700 p-1.5 text-gray-300 transition-colors hover:bg-gray-600"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>

      {/* Inline Section Rewrite */}
      {selectedText && (
        <div className="mt-2 rounded-lg border border-indigo-800 bg-indigo-950/30 p-4 animate-in fade-in slide-in-from-top-2">
          <div className="text-xs text-indigo-400 mb-2 font-medium">
            <Wand2 size={12} className="inline mr-1" />
            Rewrite Selected Section
          </div>
          <p className="text-xs text-gray-300 italic mb-3">"{selectedText.substring(0, 80)}{selectedText.length > 80 ? '...' : ''}"</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={rewriteCommand}
              onChange={(e) => setRewriteCommand(e.target.value)}
              placeholder="e.g. Make this sound more aggressive"
              className="flex-1 rounded-lg border border-indigo-700/50 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:border-indigo-500 focus:outline-none"
              onKeyDown={(e) => e.key === 'Enter' && !isRewriting && handleRewriteSection()}
              disabled={isRewriting}
            />
            <button
              onClick={handleRewriteSection}
              disabled={!rewriteCommand.trim() || isRewriting}
              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
            >
              {isRewriting ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
              Rewrite
            </button>
          </div>
        </div>
      )}

      {/* Regenerate Section */}
      <div className="rounded-lg border border-gray-800 bg-gray-950 p-4">
        <button
          onClick={() => setShowFeedback(!showFeedback)}
          className="flex items-center gap-2 text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          <RotateCcw size={16} />
          Regenerate with Adjustments
        </button>
        {showFeedback && (
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="E.g. Make it more aggressive, remove the third point..."
              className="flex-1 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:border-indigo-500 focus:outline-none"
              onKeyDown={(e) => e.key === 'Enter' && !isRegenerating && handleRegenerate()}
              disabled={isRegenerating}
            />
            <button
              onClick={handleRegenerate}
              disabled={!feedback.trim() || isRegenerating}
              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
            >
              {isRegenerating ? <Loader2 size={16} className="animate-spin" /> : <RotateCcw size={16} />}
              Apply
            </button>
          </div>
        )}
      </div>

      {/* Score grid */}
      <div className="grid grid-cols-4 gap-3">
        {scores.map(({ label, value }) => (
          <div
            key={label}
            className="rounded-lg border border-gray-800 bg-gray-950 p-3 text-center"
          >
            <p className="text-xs font-medium text-gray-400">{label}</p>
            <p className="text-lg font-bold text-gray-100">
              {(value * 100).toFixed(0)}%
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
