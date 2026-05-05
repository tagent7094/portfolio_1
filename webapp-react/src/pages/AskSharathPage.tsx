import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageCircle, ThumbsUp, MessageSquare, Repeat2, ArrowRight, ChevronDown } from 'lucide-react'

interface Post {
  content: string
  likes: number
  comments: number
  reposts: number
}

export default function AskSharathPage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [posts, setPosts] = useState<Post[]>([])
  const [visiblePosts, setVisiblePosts] = useState(10)
  const [expandedPosts, setExpandedPosts] = useState<Set<number>>(new Set())

  useEffect(() => {
    fetch('/api/chat/posts')
      .then((r) => r.json())
      .then((d) => setPosts(d.posts || []))
      .catch(() => {})
  }, [])

  const handleAsk = () => {
    if (!query.trim()) return
    navigate(`/chat?q=${encodeURIComponent(query.trim())}`)
  }

  const toggleExpand = (idx: number) => {
    setExpandedPosts((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  return (
    <div className="min-h-screen bg-[var(--page-bg)]">
      {/* ── Hero ── */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-[rgba(255,255,255,0.03)] to-transparent" />
        <div className="relative mx-auto max-w-3xl px-5 pb-16 pt-20 text-center sm:pt-28">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[var(--border-3)] bg-[var(--surface-3)] px-4 py-1.5 text-[12px] tracking-wide text-[var(--text-muted)]">
            <MessageCircle size={13} />
            Powered by Sharath's knowledge graph
          </div>

          <h1
            className="font-[var(--font-display)] text-[36px] font-bold leading-[1.15] tracking-tight text-[var(--text-primary)] sm:text-[52px]"
            style={{ animationDelay: '60ms' }}
          >
            Ask{' '}
            <span className="bg-gradient-to-r from-white to-[rgba(255,255,255,0.5)] bg-clip-text text-transparent">
              Sharath
            </span>
          </h1>

          <p className="mx-auto mt-4 max-w-lg text-[15px] leading-relaxed text-[var(--text-secondary)] sm:text-[17px]">
            Startup strategy, AI, fundraising, hiring, leadership —
            get Sharath's perspective on anything a founder would ask.
          </p>

          {/* ── Search bar ── */}
          <div className="mx-auto mt-8 max-w-xl">
            <div className="flex items-center gap-2 rounded-2xl border border-[var(--border-3)] bg-[var(--surface-2)] p-2 shadow-[var(--shadow-lg)] transition-all focus-within:border-[rgba(255,255,255,0.2)] focus-within:shadow-[0_0_0_4px_rgba(255,255,255,0.04)]">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
                placeholder="What do you think about product-market fit?"
                className="flex-1 bg-transparent px-4 py-3 text-[15px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
              />
              <button
                onClick={handleAsk}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white text-black transition-transform hover:scale-105 active:scale-95"
              >
                <ArrowRight size={18} />
              </button>
            </div>

            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {['Product-market fit', 'Hiring advice', 'Series B fundraising', 'AI in customer support'].map(
                (suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => {
                      setQuery(suggestion)
                      navigate(`/chat?q=${encodeURIComponent(suggestion)}`)
                    }}
                    className="rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] px-3 py-1.5 text-[12px] text-[var(--text-muted)] transition-colors hover:border-[var(--border-3)] hover:text-[var(--text-secondary)]"
                  >
                    {suggestion}
                  </button>
                ),
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Post feed ── */}
      {posts.length > 0 && (
        <section className="mx-auto max-w-2xl px-5 pb-20">
          <div className="mb-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-[var(--border-1)]" />
            <span className="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              {posts.length} LinkedIn Posts
            </span>
            <div className="h-px flex-1 bg-[var(--border-1)]" />
          </div>

          <div className="space-y-4">
            {posts.slice(0, visiblePosts).map((post, idx) => {
              const isExpanded = expandedPosts.has(idx)
              const isLong = post.content.length > 400
              const displayContent = isLong && !isExpanded
                ? post.content.slice(0, 400) + '…'
                : post.content

              return (
                <article
                  key={idx}
                  className="animate-fade-in rounded-xl border border-[var(--border-1)] bg-[var(--surface-2)] p-5 transition-colors hover:border-[var(--border-3)]"
                >
                  {/* Author line */}
                  <div className="mb-3 flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--surface-4)] text-[13px] font-bold text-[var(--text-secondary)]">
                      SK
                    </div>
                    <div>
                      <p className="text-[13px] font-semibold text-[var(--text-primary)]">
                        Sharath Keshava Narayana
                      </p>
                      <p className="text-[11px] text-[var(--text-muted)]">CEO, Sanas · Founder, Carya Venture Partners</p>
                    </div>
                  </div>

                  {/* Post content */}
                  <p className="whitespace-pre-line text-[13.5px] leading-[1.7] text-[var(--text-secondary)]">
                    {displayContent}
                  </p>
                  {isLong && (
                    <button
                      onClick={() => toggleExpand(idx)}
                      className="mt-1 text-[12px] font-medium text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
                    >
                      {isExpanded ? 'Show less' : '…show more'}
                    </button>
                  )}

                  {/* Engagement */}
                  <div className="mt-4 flex items-center gap-5 border-t border-[var(--border-2)] pt-3 text-[12px] text-[var(--text-muted)]">
                    <span className="flex items-center gap-1.5">
                      <ThumbsUp size={13} /> {post.likes}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <MessageSquare size={13} /> {post.comments}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Repeat2 size={13} /> {post.reposts}
                    </span>
                  </div>
                </article>
              )
            })}
          </div>

          {visiblePosts < posts.length && (
            <div className="mt-6 text-center">
              <button
                onClick={() => setVisiblePosts((v) => v + 10)}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] px-5 py-2.5 text-[13px] text-[var(--text-secondary)] transition-colors hover:border-[var(--border-3)] hover:text-[var(--text-primary)]"
              >
                <ChevronDown size={14} />
                Load more posts
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
