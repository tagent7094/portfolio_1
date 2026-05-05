import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Send, Settings, X, Key, Cpu, Loader2, AlertCircle, User, Bot,
} from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const MODELS = [
  { id: 'claude-sonnet-4-6', label: 'Sonnet 4.6' },
  { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5' },
  { id: 'claude-opus-4-6', label: 'Opus 4.6' },
]

const LS_KEY = 'asksharath_api_key'
const LS_MODEL = 'asksharath_model'

export default function ChatPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const initialQuery = searchParams.get('q') || ''

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const [apiKey, setApiKey] = useState(() => localStorage.getItem(LS_KEY) || '')
  const [model, setModel] = useState(() => localStorage.getItem(LS_MODEL) || 'claude-sonnet-4-6')

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const initialSent = useRef(false)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => scrollToBottom(), [messages, scrollToBottom])

  useEffect(() => {
    localStorage.setItem(LS_KEY, apiKey)
  }, [apiKey])

  useEffect(() => {
    localStorage.setItem(LS_MODEL, model)
  }, [model])

  const sendMessage = useCallback(
    async (userMessage: string) => {
      if (!userMessage.trim()) return
      if (!apiKey) {
        setSettingsOpen(true)
        setError('Please set your Claude API key first.')
        return
      }

      setError(null)
      const newMessages: Message[] = [...messages, { role: 'user', content: userMessage }]
      setMessages(newMessages)
      setInput('')
      setStreaming(true)

      try {
        // 1. Get RAG context
        const ctxRes = await fetch('/api/chat/context', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: userMessage, n_results: 8 }),
        })
        if (!ctxRes.ok) throw new Error('Failed to retrieve context')
        const ctx = await ctxRes.json()

        // 2. Build system prompt with retrieved chunks
        let systemPrompt = ctx.system_prompt || ''
        if (ctx.chunks && ctx.chunks.length > 0) {
          systemPrompt += '\n\n## Relevant context from your posts, stories, and knowledge graph\n\n'
          for (const chunk of ctx.chunks) {
            systemPrompt += `[${chunk.source_type}]\n${chunk.text}\n\n---\n\n`
          }
          systemPrompt +=
            '\nUse the context above to inform your response. Reference specific experiences and beliefs when relevant. Do not quote the context verbatim — synthesize it into your natural voice.'
        }

        // 3. Stream response from Claude via backend proxy
        const controller = new AbortController()
        abortRef.current = controller

        const streamRes = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
            model,
            api_key: apiKey,
            system: systemPrompt,
          }),
          signal: controller.signal,
        })

        if (!streamRes.ok) {
          const errText = await streamRes.text()
          throw new Error(errText || `HTTP ${streamRes.status}`)
        }
        if (!streamRes.body) throw new Error('No response body')

        const reader = streamRes.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let assistantText = ''

        // Add empty assistant message
        setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed || !trimmed.startsWith('data: ')) continue
            try {
              const event = JSON.parse(trimmed.substring(6))
              if (event.type === 'text') {
                assistantText += event.text
                setMessages((prev) => {
                  const updated = [...prev]
                  updated[updated.length - 1] = { role: 'assistant', content: assistantText }
                  return updated
                })
              } else if (event.type === 'error') {
                setError(event.error)
              }
            } catch {
              // skip parse errors
            }
          }
        }
      } catch (e: any) {
        if (e.name !== 'AbortError') {
          setError(e.message || 'Something went wrong')
        }
      } finally {
        setStreaming(false)
        abortRef.current = null
      }
    },
    [apiKey, model, messages],
  )

  // Auto-send initial query from URL
  useEffect(() => {
    if (initialQuery && !initialSent.current) {
      initialSent.current = true
      setInput(initialQuery)
      sendMessage(initialQuery)
    }
  }, [initialQuery, sendMessage])

  const handleSubmit = () => {
    if (streaming) {
      abortRef.current?.abort()
      return
    }
    sendMessage(input)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex h-[100dvh] flex-col bg-[var(--page-bg)]">
      {/* ── Header ── */}
      <header className="flex items-center justify-between border-b border-[var(--border-1)] px-4 py-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="font-[var(--font-display)] text-[15px] font-semibold text-[var(--text-primary)]">
              Ask Sharath
            </h1>
            <p className="text-[11px] text-[var(--text-muted)]">
              {MODELS.find((m) => m.id === model)?.label || model}
            </p>
          </div>
        </div>
        <button
          onClick={() => setSettingsOpen(!settingsOpen)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]"
        >
          <Settings size={16} />
        </button>
      </header>

      {/* ── Settings panel ── */}
      {settingsOpen && (
        <div className="animate-slide-up border-b border-[var(--border-1)] bg-[var(--surface-2)] px-4 py-4">
          <div className="mx-auto flex max-w-2xl flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                <Key size={11} className="mr-1 inline" />
                Claude API Key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-ant-..."
                className="field"
              />
            </div>
            <div className="w-full sm:w-48">
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                <Cpu size={11} className="mr-1 inline" />
                Model
              </label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="field"
              >
                {MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={() => setSettingsOpen(false)}
              className="flex h-[38px] w-8 items-center justify-center rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ── Error banner ── */}
      {error && (
        <div className="flex items-center gap-2 border-b border-[var(--error-dim)] bg-[var(--error-dim)] px-4 py-2 text-[13px] text-[var(--error)]">
          <AlertCircle size={14} />
          {error}
          <button onClick={() => setError(null)} className="ml-auto">
            <X size={14} />
          </button>
        </div>
      )}

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-2xl space-y-6">
          {messages.length === 0 && (
            <div className="py-20 text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--surface-3)]">
                <Bot size={24} className="text-[var(--text-muted)]" />
              </div>
              <p className="text-[15px] font-medium text-[var(--text-secondary)]">
                Ask me anything about startups, AI, fundraising, or leadership.
              </p>
              <p className="mt-1 text-[13px] text-[var(--text-muted)]">
                I'll respond with Sharath's perspective, grounded in his experiences and beliefs.
              </p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
              {msg.role === 'assistant' && (
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-4)] text-[11px] font-bold text-[var(--text-secondary)]">
                  SK
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-[14px] leading-[1.7] ${
                  msg.role === 'user'
                    ? 'bg-white text-black'
                    : 'bg-[var(--surface-2)] text-[var(--text-secondary)] border border-[var(--border-1)]'
                }`}
              >
                {msg.role === 'assistant' ? (
                  <div className="whitespace-pre-wrap">{msg.content || '…'}</div>
                ) : (
                  msg.content
                )}
              </div>
              {msg.role === 'user' && (
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-[11px] font-bold text-black">
                  <User size={14} />
                </div>
              )}
            </div>
          ))}

          {streaming && (
            <div className="flex items-center gap-2 text-[12px] text-[var(--text-muted)]">
              <Loader2 size={13} className="animate-spin" />
              Thinking…
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* ── Input ── */}
      <div className="border-t border-[var(--border-1)] bg-[var(--surface-1)] px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything…"
            rows={1}
            className="field min-h-[42px] max-h-[140px] resize-none"
            style={{ lineHeight: '1.5' }}
          />
          <button
            onClick={handleSubmit}
            disabled={!input.trim() && !streaming}
            className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-xl bg-white text-black transition-all hover:scale-105 active:scale-95 disabled:opacity-30 disabled:hover:scale-100"
          >
            {streaming ? <X size={16} /> : <Send size={16} />}
          </button>
        </div>
        <p className="mx-auto mt-2 max-w-2xl text-center text-[10px] text-[var(--text-muted)]">
          Responses are AI-generated based on Sharath's content. Your API key is stored locally and never saved on the server.
        </p>
      </div>
    </div>
  )
}
