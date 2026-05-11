import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Loader2, Copy, RefreshCw, Check } from 'lucide-react'
import { VARIANT_ACCENT } from './pack-table/types'

interface SelectedVariant {
  letter: string
  opener: string
  originalBody: string
}

interface Props {
  variant: SelectedVariant
  founderSlug: string
  apiKey: string
  effort: string
  voiceMarkers: string
  onClose: () => void
  onPostReady: (post: string) => void
}

export default function PostCustomizer({ variant, founderSlug, apiKey, effort, voiceMarkers, onClose, onPostReady }: Props) {
  const [streaming, setStreaming] = useState(false)
  const [streamedText, setStreamedText] = useState('')
  const [finalText, setFinalText] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const textRef = useRef<HTMLDivElement>(null)

  const runBlend = useCallback(async () => {
    if (!apiKey) {
      setError('API key required — set it in Config')
      return
    }
    setStreaming(true)
    setStreamedText('')
    setFinalText('')
    setError('')

    const abort = new AbortController()
    abortRef.current = abort

    try {
      const res = await fetch('/api/customize-post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original_post: variant.originalBody,
          selected_opener: variant.opener,
          variant_letter: variant.letter,
          founder_slug: founderSlug,
          voice_markers: voiceMarkers,
          api_key: apiKey,
          effort,
        }),
        signal: abort.signal,
        credentials: 'include',
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      if (!res.body) throw new Error('No response body')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(trimmed.substring(6))
            if (evt.type === 'text') {
              accumulated += evt.text
              setStreamedText(accumulated)
            } else if (evt.type === 'done') {
              const full = evt.full_text || accumulated
              setFinalText(full)
              onPostReady(full)
            } else if (evt.type === 'error') {
              setError(evt.error)
            }
          } catch { /* skip parse errors */ }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') setError(e?.message || 'Blend failed')
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }, [variant, founderSlug, apiKey, effort, voiceMarkers, onPostReady])

  useEffect(() => {
    runBlend()
    return () => { abortRef.current?.abort() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (textRef.current) textRef.current.scrollTop = textRef.current.scrollHeight
  }, [streamedText])

  const displayText = finalText || streamedText
  const accent = VARIANT_ACCENT[variant.letter] || VARIANT_ACCENT.A

  const handleCopy = () => {
    navigator.clipboard.writeText(displayText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border-2)' }}>
        <div className="flex items-center gap-2.5">
          <span className={`inline-flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold ${accent.badge}`}>
            {variant.letter}
          </span>
          <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
            Customizing Post
          </span>
          {streaming && <Loader2 size={13} className="animate-spin" style={{ color: 'var(--text-muted)' }} />}
        </div>
        <button onClick={onClose} className="transition-opacity hover:opacity-70" style={{ color: 'var(--text-muted)' }}>
          <X size={15} />
        </button>
      </div>

      {/* Selected opener preview */}
      <div className="px-4 py-2.5 border-b" style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
        <div className="text-[9px] font-semibold uppercase tracking-widest mb-1" style={{ color: 'var(--text-faint)' }}>
          Selected Opener
        </div>
        <p className="text-[12px] leading-relaxed italic" style={{ color: 'var(--text-secondary)' }}>
          {variant.opener}
        </p>
      </div>

      {/* Blended post output */}
      <div
        ref={textRef}
        className="px-4 py-3 text-[13px] leading-[1.8] whitespace-pre-wrap overflow-y-auto"
        style={{ color: 'var(--text-primary)', maxHeight: '350px', minHeight: '120px' }}
      >
        {displayText || (streaming ? '' : 'Waiting...')}
        {streaming && <span className="inline-block w-[2px] h-[14px] ml-0.5 animate-pulse" style={{ backgroundColor: 'var(--text-primary)' }} />}
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mb-3 rounded-lg px-3 py-2 text-[12px]" style={{ backgroundColor: 'var(--error-dim)', color: 'var(--error)' }}>
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-3 border-t" style={{ borderColor: 'var(--border-2)' }}>
        <button
          onClick={handleCopy}
          disabled={!displayText}
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] transition-colors disabled:opacity-40"
          style={{ borderColor: 'var(--border-1)', color: 'var(--text-secondary)' }}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
        <button
          onClick={runBlend}
          disabled={streaming}
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] transition-colors disabled:opacity-40"
          style={{ borderColor: 'var(--border-1)', color: 'var(--text-secondary)' }}
        >
          <RefreshCw size={12} className={streaming ? 'animate-spin' : ''} />
          Regenerate
        </button>
      </div>
    </div>
  )
}
