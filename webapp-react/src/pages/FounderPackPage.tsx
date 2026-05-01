import { useEffect, useState, useCallback } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, FileSpreadsheet, Calendar, ChevronDown,
  Loader2, X, BookOpen, Lightbulb, Quote, CheckCircle2,
} from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'

interface Pack {
  filename: string
  date: string
  size_kb: number
}

interface PostRow {
  'Row #': number
  'File': string
  'Source #': number
  'Type': string
  'Source Quote': string
  'Mechanic': string
  'Final Post': string
  'Status (Editor)': string
  'Status (Feedback)': string
  'Post Topic (derived from body)': string
  'Domain': string
  'Current Score (pts)': number
  'Buried Gold (from this post\'s paras 2-4)': string
  'Weakness': string
  'A - Opening': string
  'A - Rewrite Type': string
  'A - Key Change': string
  'A - Expected Lift': number
  'B - Opening': string
  'B - Rewrite Type': string
  'B - Key Change': string
  'B - Expected Lift': number
  'C - Opening': string
  'C - Rewrite Type': string
  'C - Key Change': string
  'C - Expected Lift': number
  'D - Opening': string
  'D - Rewrite Type': string
  'D - Key Change': string
  'D - Expected Lift': number
  'E - Opening': string
  'E - Rewrite Type': string
  'E - Key Change': string
  'Finalized Post': string
  'Recommended': string
  'Why': string
  [key: string]: any
}

interface PackData {
  readme: Record<string, string>
  headers: string[]
  posts: PostRow[]
}

const VARIANTS = ['A', 'B', 'C', 'D', 'E'] as const

function truncate(text: string, max = 120): string {
  if (!text) return ''
  const s = String(text)
  return s.length > max ? s.slice(0, max) + '…' : s
}

function RecommendedBadge({ variant }: { variant: string }) {
  if (!variant) return <span className="text-white/20 text-xs">—</span>
  return (
    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-white text-[11px] font-bold text-black">
      {variant}
    </span>
  )
}

function ScoreDots({ score }: { score: number }) {
  return (
    <span className="inline-flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className={clsx(
            'h-1.5 w-1.5 rounded-full',
            i <= score ? 'bg-white' : 'bg-white/15',
          )}
        />
      ))}
    </span>
  )
}

function PostModal({ post, onClose }: { post: PostRow; onClose: () => void }) {
  const rec = post['Recommended'] || ''

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-end bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative h-screen w-full max-w-2xl overflow-y-auto bg-[#0a0a0a] border-l border-white/10 animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Panel header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/10 bg-[#0a0a0a]/95 backdrop-blur px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-white/40">#{post['Row #']}</span>
            <span className="rounded bg-white/10 px-2 py-0.5 font-mono text-xs text-white/70">
              {post['Type']}
            </span>
            {rec && (
              <span className="flex items-center gap-1 rounded bg-white px-2 py-0.5 text-[11px] font-bold text-black">
                <CheckCircle2 size={11} /> Rec: {rec}
              </span>
            )}
          </div>
          <button onClick={onClose} className="text-white/40 hover:text-white">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-6 p-6">
          {/* Final post */}
          <section>
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">
              <BookOpen size={12} /> Final Post
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-white/90 leading-relaxed whitespace-pre-wrap">
              {post['Final Post'] || '—'}
            </div>
          </section>

          {/* Why recommended */}
          {post['Why'] && (
            <section>
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">
                <Lightbulb size={12} /> Why this variant
              </div>
              <p className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm text-white/70 leading-relaxed">
                {post['Why']}
              </p>
            </section>
          )}

          {/* Source quote */}
          {post['Source Quote'] && (
            <section>
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">
                <Quote size={12} /> Source
              </div>
              <blockquote className="rounded-xl border-l-2 border-white/20 bg-white/[0.02] pl-4 pr-4 py-3 text-xs text-white/50 leading-relaxed italic">
                {post['Source Quote']}
              </blockquote>
              {post['Mechanic'] && (
                <p className="mt-2 text-[11px] text-white/30">
                  Mechanic: {post['Mechanic']}
                </p>
              )}
            </section>
          )}

          {/* Opening variants */}
          <section>
            <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">
              Opening variants
            </div>
            <div className="space-y-2">
              {VARIANTS.map((v) => {
                const opening = post[`${v} - Opening`]
                const rewriteType = post[`${v} - Rewrite Type`]
                const lift = post[`${v} - Expected Lift`]
                if (!opening) return null
                const isRec = rec === v
                return (
                  <div
                    key={v}
                    className={clsx(
                      'rounded-lg border p-3 text-sm',
                      isRec
                        ? 'border-white/30 bg-white/[0.06]'
                        : 'border-white/8 bg-white/[0.02]',
                    )}
                  >
                    <div className="mb-1.5 flex items-center gap-2">
                      <span
                        className={clsx(
                          'inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold',
                          isRec ? 'bg-white text-black' : 'bg-white/10 text-white/60',
                        )}
                      >
                        {v}
                      </span>
                      {rewriteType && (
                        <span className="text-[10px] text-white/30">{rewriteType}</span>
                      )}
                      {lift !== undefined && lift !== '' && (
                        <span className="ml-auto">
                          <ScoreDots score={Number(lift)} />
                        </span>
                      )}
                    </div>
                    <p className="text-white/80 leading-snug">{opening}</p>
                  </div>
                )
              })}
            </div>
          </section>

          {/* Meta */}
          <section className="grid grid-cols-2 gap-3 text-xs">
            {post['Post Topic (derived from body)'] && (
              <div className="rounded-lg border border-white/8 bg-white/[0.02] p-3">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-white/30">Topic</div>
                <div className="text-white/70">{post['Post Topic (derived from body)']}</div>
              </div>
            )}
            {post['Domain'] && (
              <div className="rounded-lg border border-white/8 bg-white/[0.02] p-3">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-white/30">Domain</div>
                <div className="text-white/70">{post['Domain']}</div>
              </div>
            )}
            {post['Weakness'] && (
              <div className="col-span-2 rounded-lg border border-white/8 bg-white/[0.02] p-3">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-white/30">Weakness</div>
                <div className="text-white/60">{post['Weakness']}</div>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

export default function FounderPackPage() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const [authed, setAuthed] = useState<boolean | null>(null)
  const [packs, setPacks] = useState<Pack[]>([])
  const [selectedDate, setSelectedDate] = useState<string>(searchParams.get('date') || '')
  const [packData, setPackData] = useState<PackData | null>(null)
  const [loadingPacks, setLoadingPacks] = useState(true)
  const [loadingData, setLoadingData] = useState(false)
  const [selectedPost, setSelectedPost] = useState<PostRow | null>(null)
  const [filterSource, setFilterSource] = useState<string>('all')

  // Admin auth check
  useEffect(() => {
    apiGet('/api/admin/me')
      .then(() => setAuthed(true))
      .catch(() => {
        setAuthed(false)
        navigate('/admin/login', { replace: true })
      })
  }, [navigate])

  // Load available packs list
  useEffect(() => {
    if (!authed || !slug) return
    setLoadingPacks(true)
    apiGet<{ packs: Pack[] }>(`/api/admin/founders/${slug}/post-packs`)
      .then((d) => {
        setPacks(d.packs)
        if (!selectedDate && d.packs.length > 0) {
          setSelectedDate(d.packs[0].date)
        }
      })
      .catch(() => {})
      .finally(() => setLoadingPacks(false))
  }, [authed, slug])

  // Load pack data when date changes
  const loadPackData = useCallback(async (date: string) => {
    if (!slug || !date) return
    setLoadingData(true)
    setPackData(null)
    setFilterSource('all')
    try {
      const data = await apiGet<PackData>(`/api/admin/founders/${slug}/post-packs/${date}`)
      setPackData(data)
    } catch {
      setPackData(null)
    } finally {
      setLoadingData(false)
    }
  }, [slug])

  useEffect(() => {
    if (authed && selectedDate) {
      setSearchParams(selectedDate ? { date: selectedDate } : {}, { replace: true })
      loadPackData(selectedDate)
    }
  }, [authed, selectedDate, loadPackData])

  if (authed === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <Loader2 size={20} className="animate-spin text-white" />
      </div>
    )
  }

  const displayName = slug ? slug.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : ''

  // Unique source batches for filter
  const sourceBatches = packData
    ? [...new Set(packData.posts.map((p) => p['File']).filter(Boolean))]
    : []

  const filteredPosts = packData
    ? filterSource === 'all'
      ? packData.posts
      : packData.posts.filter((p) => p['File'] === filterSource)
    : []

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <div className="sticky top-0 z-20 border-b border-white/10 bg-black/95 backdrop-blur">
        <div className="mx-auto max-w-screen-xl px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/admin')}
              className="flex items-center gap-1.5 text-sm text-white/50 hover:text-white transition-colors"
            >
              <ArrowLeft size={15} /> Admin
            </button>
            <span className="text-white/20">/</span>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-xs font-semibold">
                {displayName.charAt(0)}
              </div>
              <span className="font-[var(--font-display)] font-semibold">{displayName}</span>
            </div>
          </div>

          {/* Date picker */}
          <div className="flex items-center gap-2">
            <Calendar size={14} className="text-white/40" />
            {loadingPacks ? (
              <Loader2 size={14} className="animate-spin text-white/40" />
            ) : packs.length === 0 ? (
              <span className="text-xs text-white/30">No packs yet</span>
            ) : (
              <div className="relative">
                <select
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="appearance-none rounded-lg border border-white/10 bg-white/[0.04] pl-3 pr-8 py-1.5 text-sm text-white focus:outline-none focus:border-white/30 cursor-pointer"
                >
                  {packs.map((p) => (
                    <option key={p.date} value={p.date} className="bg-black">
                      {p.date} · {p.filename}
                    </option>
                  ))}
                </select>
                <ChevronDown size={12} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-white/40" />
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-screen-xl px-6 py-6 space-y-6">
        {/* README summary card */}
        {packData && Object.keys(packData.readme).length > 0 && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
            <div className="flex items-center gap-2 mb-4">
              <FileSpreadsheet size={15} className="text-white/40" />
              <span className="text-xs font-semibold uppercase tracking-wider text-white/40">Pack Summary</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Object.entries(packData.readme)
                .filter(([k]) => k !== 'null')
                .map(([key, val]) => (
                  <div key={key}>
                    <div className="text-[10px] uppercase tracking-wider text-white/30 mb-1">{key}</div>
                    <div className="text-sm text-white/80 leading-snug">{val}</div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Source filter + post count */}
        {packData && packData.posts.length > 0 && (
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => setFilterSource('all')}
                className={clsx(
                  'rounded-lg border px-3 py-1 text-xs transition-colors',
                  filterSource === 'all'
                    ? 'border-white/30 bg-white/10 text-white'
                    : 'border-white/10 text-white/40 hover:text-white/70',
                )}
              >
                All ({packData.posts.length})
              </button>
              {sourceBatches.map((batch) => (
                <button
                  key={batch}
                  onClick={() => setFilterSource(batch)}
                  className={clsx(
                    'rounded-lg border px-3 py-1 text-xs transition-colors max-w-[200px] truncate',
                    filterSource === batch
                      ? 'border-white/30 bg-white/10 text-white'
                      : 'border-white/10 text-white/40 hover:text-white/70',
                  )}
                >
                  {batch}
                </button>
              ))}
            </div>
            <span className="text-xs text-white/30">
              {filteredPosts.length} post{filteredPosts.length !== 1 ? 's' : ''}
            </span>
          </div>
        )}

        {/* Loading state */}
        {loadingData && (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={20} className="animate-spin text-white/40" />
          </div>
        )}

        {/* Empty state */}
        {!loadingData && !loadingPacks && packs.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <FileSpreadsheet size={32} className="mb-4 text-white/20" />
            <p className="text-sm text-white/40">No post packs yet for {displayName}.</p>
            <p className="mt-1 text-xs text-white/25">
              Add Excel files to{' '}
              <code className="rounded bg-white/10 px-1 text-[11px]">
                data/founders/{slug}/post-data/
              </code>
            </p>
          </div>
        )}

        {/* Posts table */}
        {!loadingData && packData && filteredPosts.length > 0 && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.02] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-white/40 w-10">#</th>
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-white/40">Source batch</th>
                    <th className="px-3 py-3 text-center text-[10px] font-semibold uppercase tracking-wider text-white/40 w-16">Type</th>
                    <th className="px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-white/40">Topic</th>
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-white/40">Post preview</th>
                    <th className="px-3 py-3 text-center text-[10px] font-semibold uppercase tracking-wider text-white/40 w-16">Rec</th>
                    <th className="px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-white/40">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPosts.map((post, idx) => (
                    <tr
                      key={idx}
                      onClick={() => setSelectedPost(post)}
                      className="border-b border-white/5 hover:bg-white/[0.03] cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-white/30">
                        {post['Row #']}
                      </td>
                      <td className="px-4 py-3 text-xs text-white/50 max-w-[160px] truncate">
                        {post['File']}
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span className="rounded bg-white/8 px-2 py-0.5 font-mono text-[11px] text-white/60">
                          {post['Type']}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-xs text-white/60 max-w-[180px]">
                        <span className="line-clamp-2">{post['Post Topic (derived from body)']}</span>
                      </td>
                      <td className="px-4 py-3 max-w-xs">
                        <span className="text-xs text-white/70 line-clamp-2 leading-relaxed">
                          {truncate(post['Final Post'], 150)}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <RecommendedBadge variant={post['Recommended']} />
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex flex-col gap-0.5">
                          {post['Status (Editor)'] && (
                            <span className="text-[10px] text-white/40">{post['Status (Editor)']}</span>
                          )}
                          {post['Status (Feedback)'] && (
                            <span className="text-[10px] text-white/30">{post['Status (Feedback)']}</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Detail modal */}
      {selectedPost && (
        <PostModal post={selectedPost} onClose={() => setSelectedPost(null)} />
      )}
    </div>
  )
}
