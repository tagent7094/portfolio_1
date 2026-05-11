import { useState, useRef, useEffect } from 'react'
import { MessageSquare, X, Send, Loader2, Minus } from 'lucide-react'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface Props {
  currentPost: string
  onPostUpdate: (newPost: string) => void
  founderSlug: string
  apiKey: string
  effort: string
  voiceMarkers: string
}

export default function CornerChatbot({ currentPost, onPostUpdate, founderSlug, apiKey, effort, voiceMarkers }: Props) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, streamingText])

  const sendMessage = async () => {
    const msg = input.trim()
    if (!msg || streaming || !apiKey) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setStreaming(true)
    setStreamingText('')

    const abort = new AbortController()
    abortRef.current = abort

    try {
      const res = await fetch('/api/customize-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_post: currentPost,
          message: msg,
          founder_slug: founderSlug,
          voice_markers: voiceMarkers,
          api_key: apiKey,
          effort,
        }),
        signal: abort.signal,
        credentials: 'include',
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      if (!res.body) throw new Error('No body')

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
              setStreamingText(accumulated)
            } else if (evt.type === 'done') {
              const full = evt.full_text || accumulated
              setMessages(prev => [...prev, { role: 'assistant', content: full }])
              setStreamingText('')
              onPostUpdate(full)
            } else if (evt.type === 'error') {
              setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${evt.error}` }])
              setStreamingText('')
            }
          } catch { /* skip */ }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e?.message}` }])
        setStreamingText('')
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition-transform hover:scale-105"
        style={{ backgroundColor: 'var(--text-primary)', color: 'var(--surface-1)' }}
      >
        <MessageSquare size={20} />
      </button>
    )
  }

  return (
    <div
      className="fixed bottom-5 right-5 z-50 flex flex-col rounded-xl border shadow-2xl"
      style={{
        width: '340px',
        height: '420px',
        backgroundColor: 'var(--surface-1)',
        borderColor: 'var(--border-1)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b shrink-0" style={{ borderColor: 'var(--border-2)' }}>
        <div className="flex items-center gap-2">
          <MessageSquare size={13} style={{ color: 'var(--text-primary)' }} />
          <span className="text-[12px] font-semibold" style={{ color: 'var(--text-primary)' }}>Edit Post</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setOpen(false)} className="p-1 transition-opacity hover:opacity-70" style={{ color: 'var(--text-muted)' }}>
            <Minus size={13} />
          </button>
          <button onClick={() => { setOpen(false); setMessages([]) }} className="p-1 transition-opacity hover:opacity-70" style={{ color: 'var(--text-muted)' }}>
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {messages.length === 0 && !streaming && (
          <div className="flex items-center justify-center h-full text-center px-4">
            <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-faint)' }}>
              Tell me how to edit the post. e.g. "Make the tone more conversational" or "Shorten to 150 words"
            </p>
          </div>
        )}
        {messages.slice(-10).map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className="max-w-[85%] rounded-lg px-3 py-2 text-[11px] leading-relaxed"
              style={msg.role === 'user'
                ? { backgroundColor: 'var(--text-primary)', color: 'var(--surface-1)' }
                : { backgroundColor: 'var(--surface-2)', color: 'var(--text-secondary)', border: '1px solid var(--border-2)' }
              }
            >
              {msg.role === 'assistant'
                ? <pre className="whitespace-pre-wrap font-sans max-h-[200px] overflow-y-auto">{msg.content}</pre>
                : msg.content
              }
            </div>
          </div>
        ))}
        {streaming && streamingText && (
          <div className="flex justify-start">
            <div
              className="max-w-[85%] rounded-lg px-3 py-2 text-[11px] leading-relaxed"
              style={{ backgroundColor: 'var(--surface-2)', color: 'var(--text-secondary)', border: '1px solid var(--border-2)' }}
            >
              <pre className="whitespace-pre-wrap font-sans max-h-[200px] overflow-y-auto">{streamingText}</pre>
              <span className="inline-block w-[2px] h-[10px] ml-0.5 animate-pulse" style={{ backgroundColor: 'var(--text-primary)' }} />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t px-3 py-2.5" style={{ borderColor: 'var(--border-2)' }}>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
            placeholder="Edit instruction..."
            disabled={streaming}
            className="flex-1 rounded-lg border px-3 py-2 text-[12px] focus:outline-none focus:ring-1 disabled:opacity-50"
            style={{
              borderColor: 'var(--border-1)',
              backgroundColor: 'var(--surface-2)',
              color: 'var(--text-primary)',
            }}
          />
          <button
            onClick={sendMessage}
            disabled={streaming || !input.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-opacity disabled:opacity-30"
            style={{ backgroundColor: 'var(--text-primary)', color: 'var(--surface-1)' }}
          >
            {streaming ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          </button>
        </div>
      </div>
    </div>
  )
}
