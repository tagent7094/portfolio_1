import { useCallback, useEffect, useRef, useState } from 'react'
import { Search, ChevronLeft, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { apiGet, apiPost } from '../../api/client'
import type { PostBrowseResult, ViralPost } from '../../types/api'

interface Props {
  onSelectPost: (text: string, postId: string) => void
  selectedPostId: string | null
}

const ENGAGEMENT_OPTIONS = [
  { label: 'Any', value: 0 },
  { label: '> 100', value: 100 },
  { label: '> 500', value: 500 },
  { label: '> 1 000', value: 1000 },
  { label: '> 5 000', value: 5000 },
]

function engagementColor(score: number): string {
  if (score >= 5000) return 'bg-white/10'
  if (score >= 1000) return 'bg-white'
  if (score >= 500) return 'bg-white/20'
  if (score >= 100) return 'bg-white/20'
  return 'bg-gray-600'
}

const LIKES_OPTIONS = [
  { label: 'Any Likes', value: 0 },
  { label: '> 50', value: 50 },
  { label: '> 200', value: 200 },
  { label: '> 500', value: 500 },
  { label: '> 1000', value: 1000 },
]

const COMMENTS_OPTIONS = [
  { label: 'Any Comments', value: 0 },
  { label: '> 10', value: 10 },
  { label: '> 50', value: 50 },
  { label: '> 100', value: 100 },
  { label: '> 500', value: 500 },
]

const REPOSTS_OPTIONS = [
  { label: 'Any Reposts', value: 0 },
  { label: '> 5', value: 5 },
  { label: '> 20', value: 20 },
  { label: '> 50', value: 50 },
  { label: '> 100', value: 100 },
]

export default function PostBrowser({ onSelectPost, selectedPostId }: Props) {
  const [query, setQuery] = useState('')
  const [minEngagement, setMinEngagement] = useState(0)
  const [minLikes, setMinLikes] = useState(0)
  const [minComments, setMinComments] = useState(0)
  const [minReposts, setMinReposts] = useState(0)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<PostBrowseResult | null>(null)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const fetchPosts = useCallback(
    async (q: string, pg: number, minEng: number, mLikes: number, mComments: number, mReposts: number) => {
      setLoading(true)
      try {
        let result: PostBrowseResult
        if (q.trim()) {
          result = await apiPost<PostBrowseResult>('/api/posts/search', {
            query: q,
            page: pg,
            page_size: 20,
          })
        } else {
          const params = new URLSearchParams({
            page: String(pg),
            page_size: '20',
            sort_by: 'engagement_score',
          })
          if (minEng > 0) params.set('min_engagement', String(minEng))
          if (mLikes > 0) params.set('min_likes', String(mLikes))
          if (mComments > 0) params.set('min_comments', String(mComments))
          if (mReposts > 0) params.set('min_reposts', String(mReposts))
          result = await apiGet<PostBrowseResult>(
            `/api/posts/browse?${params.toString()}`,
          )
        }
        setData(result)
      } catch (e) {
        console.error('Failed to fetch posts:', e)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  // Initial load & filter change
  useEffect(() => {
    setPage(1)
    fetchPosts(query, 1, minEngagement, minLikes, minComments, minReposts)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minEngagement, minLikes, minComments, minReposts])

  // Debounced search
  const handleQueryChange = (val: string) => {
    setQuery(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setPage(1)
      fetchPosts(val, 1, minEngagement, minLikes, minComments, minReposts)
    }, 300)
  }

  const changePage = (pg: number) => {
    setPage(pg)
    fetchPosts(query, pg, minEngagement, minLikes, minComments, minReposts)
  }

  return (
    <div className="flex h-full flex-col space-y-3">
      {/* Search + filter row */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="Search posts..."
            className="w-full rounded-lg border border-gray-700 bg-gray-800 py-2 pl-8 pr-3 text-sm text-gray-100 placeholder:text-gray-500 focus:border-white/30 focus:outline-none"
          />
        </div>
        <select
          value={minEngagement}
          onChange={(e) => setMinEngagement(Number(e.target.value))}
          className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-2 text-xs text-gray-100 focus:border-white/30 focus:outline-none"
        >
          {ENGAGEMENT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Extra filters row */}
      <div className="flex gap-2">
        <select
          value={minLikes}
          onChange={(e) => setMinLikes(Number(e.target.value))}
          className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs text-gray-300 focus:border-white/30 focus:outline-none"
        >
          {LIKES_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select
          value={minComments}
          onChange={(e) => setMinComments(Number(e.target.value))}
          className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs text-gray-300 focus:border-white/30 focus:outline-none"
        >
          {COMMENTS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select
          value={minReposts}
          onChange={(e) => setMinReposts(Number(e.target.value))}
          className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs text-gray-300 focus:border-white/30 focus:outline-none"
        >
          {REPOSTS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {/* Post list */}
      <div className="flex-1 space-y-2 overflow-auto">
        {loading && (
          <p className="py-8 text-center text-sm text-gray-500">Loading...</p>
        )}
        {!loading && data?.posts.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-500">
            No posts found.
          </p>
        )}
        {!loading &&
          data?.posts.map((post) => (
            <PostCard
              key={post.post_id}
              post={post}
              selected={post.post_id === selectedPostId}
              onClick={() => onSelectPost(post.content, post.post_id)}
            />
          ))}
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between border-t border-gray-800 pt-2">
          <button
            disabled={page <= 1}
            onClick={() => changePage(page - 1)}
            className="flex items-center gap-1 rounded px-2 py-1 text-sm text-gray-400 transition-colors hover:bg-gray-800 disabled:opacity-40"
          >
            <ChevronLeft size={14} /> Previous
          </button>
          <span className="text-xs text-gray-500">
            Page {data.page} of {data.pages}
          </span>
          <button
            disabled={page >= data.pages}
            onClick={() => changePage(page + 1)}
            className="flex items-center gap-1 rounded px-2 py-1 text-sm text-gray-400 transition-colors hover:bg-gray-800 disabled:opacity-40"
          >
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  )
}

/* ── Small inner card component ── */

function PostCard({
  post,
  selected,
  onClick,
}: {
  post: ViralPost
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full rounded-lg border p-3 text-left transition-colors',
        selected
          ? 'border-white/30 bg-gray-800/80'
          : 'border-gray-800 bg-gray-900 hover:border-gray-700',
      )}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span
          className={clsx(
            'rounded px-1.5 py-0.5 text-xs font-semibold text-white',
            engagementColor(post.engagement_score),
          )}
        >
          {post.engagement_score.toLocaleString()}
        </span>
        <span className="text-xs text-gray-500">{post.content_type}</span>
      </div>
      <p className="mb-1.5 text-sm text-gray-300">
        {post.content.length > 150
          ? post.content.slice(0, 150) + '...'
          : post.content}
      </p>
      <div className="flex gap-3 text-xs text-gray-500">
        <span>{post.likes.toLocaleString()} likes</span>
        <span>{post.comments.toLocaleString()} comments</span>
        <span>{post.reposts.toLocaleString()} reposts</span>
      </div>
    </button>
  )
}
