import { useEffect, useState, useMemo, useRef, useCallback } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, FileSpreadsheet, Calendar, ChevronDown,
  Loader2, X, Search,
  Download, Sheet, Sun, Moon, Eye, EyeOff, Play, Cpu,
} from 'lucide-react'
import clsx from 'clsx'
import { apiGet, apiPost, streamSSE } from '../api/client'
import { useTheme } from '../hooks/useTheme'
import TraceViewer from '../components/TraceViewer'
import PostCustomizer from '../components/PostCustomizer'
import CornerChatbot from '../components/CornerChatbot'
import CustomizeSection from '../components/CustomizeSection'
import {
  ALL_GROUPS, s,
  PostTable, DetailPanel, PackSummary, exportExcel,
  type PackData,
} from '../components/pack-table'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Pack { filename: string; date: string; size_kb: number }

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FounderPackPage() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [theme, toggleTheme] = useTheme()

  const [authed, setAuthed]             = useState<boolean | null>(null)
  const [packs, setPacks]               = useState<Pack[]>([])
  const [selectedDate, setSelectedDate] = useState<string>(searchParams.get('date') ?? '')
  const [packData, setPackData]         = useState<PackData | null>(null)
  const [loadingPacks, setLoadingPacks] = useState(true)
  const [loadingData, setLoadingData]   = useState(false)
  const [selectedPost, setSelectedPost] = useState<Record<string, any> | null>(null)
  const [search, setSearch]             = useState('')
  const [visibleGroups, setVisibleGroups] = useState<Set<string>>(new Set(ALL_GROUPS))
  const [edits, setEdits]               = useState<Record<string, Record<string, string>>>({})
  const [saving, setSaving]             = useState(false)
  const [groupMenuOpen, setGroupMenuOpen] = useState(false)
  const [sheetExporting, setSheetExporting] = useState(false)

  // Batch generation state
  const [generating, setGenerating] = useState(false)
  const [genProgress, setGenProgress] = useState(0)
  const [genStage, setGenStage] = useState('')
  const [genLog, setGenLog] = useState<string[]>([])
  const [genConfig, setGenConfig] = useState(false) // config panel open
  const [nSources, setNSources] = useState(1)
  const [creativity, setCreativity] = useState(0.5)
  const genAbortRef = useRef<AbortController | null>(null)

  // Effort toggle
  const [effort, setEffort] = useState<'low' | 'medium' | 'high'>('high')

  // Detail panel + customizer state
  const [showDetail, setShowDetail] = useState(false)
  const [custVariant, setCustVariant] = useState<{ letter: string; opener: string; originalBody: string } | null>(null)
  const [custPost, setCustPost] = useState('')
  const [custApiKey, setCustApiKey] = useState(() => localStorage.getItem('asksharath_api_key') || '')

  // Trace viewer state
  const [showTraces, setShowTraces] = useState(false)
  const [traceData, setTraceData] = useState<any>(null)
  const [loadingTraces, setLoadingTraces] = useState(false)

  const handleEdit = useCallback((rowId: string, colKey: string, value: string) => {
    setEdits(prev => ({
      ...prev,
      [rowId]: { ...(prev[rowId] || {}), [colKey]: value },
    }))
  }, [])

  const editCount = useMemo(
    () => Object.values(edits).reduce((sum, row) => sum + Object.keys(row).length, 0),
    [edits],
  )

  useEffect(() => {
    apiGet('/api/admin/me')
      .then(() => setAuthed(true))
      .catch(() => { setAuthed(false); navigate('/admin/login', { replace: true }) })
  }, [navigate])

  const refreshPacks = useCallback((autoSelectLatest = false) => {
    if (!slug) return
    setLoadingPacks(true)
    apiGet<{ packs: Pack[] }>(`/api/admin/founders/${slug}/post-packs`)
      .then(d => {
        setPacks(d.packs)
        if (autoSelectLatest && d.packs.length > 0) setSelectedDate(d.packs[0].date)
        else if (!selectedDate && d.packs.length > 0) setSelectedDate(d.packs[0].date)
      })
      .catch(() => {})
      .finally(() => setLoadingPacks(false))
  }, [slug, selectedDate])

  useEffect(() => {
    if (!authed || !slug) return
    refreshPacks()
  }, [authed, slug])

  useEffect(() => {
    if (!authed || !selectedDate || !slug) return
    setSearchParams({ date: selectedDate }, { replace: true })
    setLoadingData(true)
    setPackData(null)
    setSelectedPost(null)
    setEdits({})
    apiGet<PackData>(`/api/admin/founders/${slug}/post-packs/${selectedDate}`)
      .then(d => setPackData(d))
      .catch(() => {})
      .finally(() => setLoadingData(false))
  }, [authed, selectedDate, slug])

  const filteredPosts = useMemo(() => {
    if (!packData) return []
    const q = search.trim().toLowerCase()
    if (!q) return packData.posts
    return packData.posts.filter(post =>
      packData.headers.some(h => s(post[h]).toLowerCase().includes(q))
    )
  }, [packData, search])

  const toggleGroup = (g: string) => {
    setVisibleGroups(prev => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })
  }

  const saveEdits = async () => {
    if (!packData || !slug || !selectedDate || editCount === 0) return
    setSaving(true)
    try {
      await apiPost(`/api/admin/founders/${slug}/post-packs/${selectedDate}/edits`, { edits })
    } catch {
      // silently ignore — edits are still in local state
    } finally {
      setSaving(false)
    }
  }

  const handleExcelExport = () => {
    if (!packData) return
    exportExcel(packData.posts, packData.headers, edits, `${slug}-${selectedDate}`)
  }

  const handleSheetsExport = async () => {
    if (!packData || !slug || !selectedDate) return
    setSheetExporting(true)
    try {
      const res = await apiPost<{ url: string }>(
        `/api/admin/founders/${slug}/post-packs/${selectedDate}/export-sheets`,
        { edits },
      )
      window.open(res.url, '_blank')
    } catch (e: any) {
      alert(`Google Sheets export failed: ${e?.message || 'unknown error'}`)
    } finally {
      setSheetExporting(false)
    }
  }

  const handleGenerate = async () => {
    if (!slug) return
    setGenConfig(false)
    setGenerating(true)
    setGenProgress(0)
    setGenStage('starting')
    setGenLog([])

    const abort = new AbortController()
    genAbortRef.current = abort

    try {
      await streamSSE(
        '/api/generate/batch/stream',
        { founder_slug: slug, n_sources: nSources, creativity, effort, platform: 'linkedin' },
        (event) => {
          setGenProgress(event.progress || 0)
          setGenStage(event.stage)
          setGenLog(prev => [...prev, `${event.stage}: ${event.status}`])
          if (event.status === 'pipeline_done') {
            setGenerating(false)
            refreshPacks(true)
          }
        },
        abort.signal,
      )
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        setGenLog(prev => [...prev, `error: ${e?.message || 'generation failed'}`])
      }
    } finally {
      setGenerating(false)
      genAbortRef.current = null
    }
  }

  const cancelGenerate = () => {
    genAbortRef.current?.abort()
    setGenerating(false)
    setGenConfig(false)
  }

  const loadTraces = async () => {
    if (!slug || !selectedDate) return
    if (showTraces) { setShowTraces(false); return }
    setLoadingTraces(true)
    try {
      const data = await apiGet<any>(`/api/admin/founders/${slug}/post-packs/${selectedDate}/traces`)
      setTraceData(data)
      setShowTraces(true)
    } catch {
      setTraceData(null)
      setShowTraces(false)
    } finally {
      setLoadingTraces(false)
    }
  }

  const displayName = slug?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) ?? ''

  if (authed === null) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ backgroundColor: 'var(--page-bg)' }}>
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
      </div>
    )
  }

  const navBtn = "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors"
  const navBtnStyle = { borderColor: 'var(--border-1)', color: 'var(--text-secondary)', backgroundColor: 'var(--surface-2)' }

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ backgroundColor: 'var(--page-bg)', color: 'var(--text-primary)' }}>

      {/* ── Top nav ── */}
      <div className="shrink-0 border-b backdrop-blur" style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}>

        {/* Row 1: breadcrumb + theme */}
        <div className="flex items-center gap-2 px-4 py-2.5">
          <button
            onClick={() => navigate('/admin')}
            className="flex items-center gap-1.5 text-xs transition-opacity hover:opacity-70"
            style={{ color: 'var(--text-muted)' }}
          >
            <ArrowLeft size={13} /> <span className="hidden sm:inline">Admin</span>
          </button>
          <span style={{ color: 'var(--text-faint)' }}>/</span>
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-bold"
              style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}>
              {displayName.charAt(0)}
            </div>
            <span className="font-[var(--font-display)] font-semibold text-sm truncate">{displayName}</span>
          </div>

          <div className="flex-1" />

          {/* Theme toggle — always visible */}
          <button
            onClick={toggleTheme}
            className="flex items-center justify-center h-7 w-7 rounded-lg border transition-colors shrink-0"
            style={navBtnStyle}
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          >
            {theme === 'dark' ? <Sun size={13} /> : <Moon size={13} />}
          </button>
        </div>

        {/* Row 2: date + actions */}
        <div className="flex items-center gap-2 px-4 pb-2.5 flex-wrap">

          {/* Date picker */}
          <div className="flex items-center gap-1.5 min-w-0">
            <Calendar size={12} style={{ color: 'var(--text-muted)' }} className="shrink-0" />
            {loadingPacks ? (
              <Loader2 size={12} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
            ) : packs.length > 0 ? (
              <div className="relative min-w-0">
                <select
                  value={selectedDate}
                  onChange={e => setSelectedDate(e.target.value)}
                  className="appearance-none rounded-lg border pl-2 pr-6 py-1.5 text-xs focus:outline-none cursor-pointer max-w-[200px] sm:max-w-xs truncate"
                  style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-2)', color: 'var(--text-primary)' }}
                >
                  {packs.map(p => (
                    <option key={p.date} value={p.date}>{p.date}</option>
                  ))}
                </select>
                <ChevronDown size={10} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
              </div>
            ) : null}
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Group toggle */}
            <div className="relative">
              <button
                onClick={() => setGroupMenuOpen(o => !o)}
                className={navBtn}
                style={navBtnStyle}
              >
                {visibleGroups.size < ALL_GROUPS.length ? <EyeOff size={12} /> : <Eye size={12} />}
                <span className="hidden sm:inline">Columns</span>
              </button>
              {groupMenuOpen && (
                <div
                  className="absolute left-0 top-full mt-1 z-50 rounded-xl border p-2 shadow-xl min-w-[160px]"
                  style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}
                >
                  {ALL_GROUPS.map(g => (
                    <label key={g} className="flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer hover:opacity-70 text-xs">
                      <input type="checkbox" checked={visibleGroups.has(g)} onChange={() => toggleGroup(g)} className="accent-white" />
                      <span style={{ color: 'var(--text-secondary)' }}>{g}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            {/* Save edits */}
            {editCount > 0 && (
              <button
                onClick={saveEdits}
                disabled={saving}
                className={navBtn}
                style={{ borderColor: '#f59e0b', color: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)' }}
              >
                {saving ? <Loader2 size={12} className="animate-spin" /> : null}
                Save {editCount}
              </button>
            )}

            {/* Excel */}
            <button onClick={handleExcelExport} disabled={!packData} className={clsx(navBtn, 'disabled:opacity-40')} style={navBtnStyle}>
              <Download size={12} /> <span className="hidden sm:inline">Excel</span>
            </button>

            {/* Sheets */}
            <button
              onClick={handleSheetsExport}
              disabled={!packData || sheetExporting}
              className={clsx(navBtn, 'disabled:opacity-40')}
              style={navBtnStyle}
              title="Export to Google Sheets"
            >
              {sheetExporting ? <Loader2 size={12} className="animate-spin" /> : <Sheet size={12} />}
              <span className="hidden sm:inline">Sheets</span>
            </button>

            {/* Generate */}
            <div className="relative">
              <button
                onClick={() => setGenConfig(o => !o)}
                disabled={generating}
                className={clsx(navBtn, 'disabled:opacity-40')}
                style={generating
                  ? { borderColor: '#a78bfa', color: '#a78bfa', backgroundColor: 'rgba(167,139,250,0.08)' }
                  : { borderColor: '#a78bfa', color: '#a78bfa', backgroundColor: 'transparent' }}
              >
                {generating ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                <span className="hidden sm:inline">{generating ? 'Generating…' : 'Generate'}</span>
              </button>

              {genConfig && !generating && (
                <div
                  className="absolute right-0 top-full mt-1 z-50 rounded-xl border p-4 shadow-xl w-[240px]"
                  style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}
                >
                  <div className="space-y-3">
                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>
                        Sources ({nSources})
                      </label>
                      <input
                        type="range" min={1} max={10} value={nSources}
                        onChange={e => setNSources(Number(e.target.value))}
                        className="w-full accent-violet-400"
                      />
                      <div className="flex justify-between text-[10px] mt-0.5" style={{ color: 'var(--text-faint)' }}>
                        <span>1</span><span>10</span>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>
                        Creativity ({creativity.toFixed(1)})
                      </label>
                      <input
                        type="range" min={0} max={1} step={0.1} value={creativity}
                        onChange={e => setCreativity(Number(e.target.value))}
                        className="w-full accent-violet-400"
                      />
                      <div className="flex justify-between text-[10px] mt-0.5" style={{ color: 'var(--text-faint)' }}>
                        <span>Conservative</span><span>Creative</span>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>
                        Effort
                      </label>
                      <div className="flex rounded-lg border overflow-hidden text-[10px]" style={{ borderColor: 'var(--border-1)' }}>
                        {(['low', 'medium', 'high'] as const).map(level => (
                          <button
                            key={level}
                            onClick={() => setEffort(level)}
                            className={`flex-1 px-2 py-1.5 capitalize transition-colors ${
                              effort === level
                                ? 'bg-violet-500 text-white'
                                : ''
                            }`}
                            style={effort !== level ? { color: 'var(--text-muted)' } : {}}
                          >
                            {level}
                          </button>
                        ))}
                      </div>
                    </div>
                    <p className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                      {nSources * 9} posts ({nSources} source{nSources !== 1 ? 's' : ''} × 9 per source)
                    </p>
                    <button
                      onClick={handleGenerate}
                      className="w-full rounded-lg py-2 text-xs font-semibold transition-colors"
                      style={{ backgroundColor: '#a78bfa', color: 'black' }}
                    >
                      Start Generation
                    </button>
                  </div>
                </div>
              )}
            {/* Traces */}
            <button
              onClick={loadTraces}
              disabled={!packData || loadingTraces}
              className={clsx(navBtn, 'disabled:opacity-40')}
              style={showTraces
                ? { borderColor: '#a78bfa', color: '#a78bfa', backgroundColor: 'rgba(167,139,250,0.08)' }
                : navBtnStyle}
              title="View pipeline traceability"
            >
              {loadingTraces ? <Loader2 size={12} className="animate-spin" /> : <Cpu size={12} />}
              <span className="hidden sm:inline">Traces</span>
            </button>
            </div>
          </div>
        </div>

        {/* Search bar */}
        <div className="border-t px-4 py-2" style={{ borderColor: 'var(--border-2)' }}>
          <div className="relative">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="Search all columns…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full rounded-lg border pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-1"
              style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-2)', color: 'var(--text-primary)' }}
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}>
                <X size={11} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Generation progress overlay */}
      {generating && (
        <div className="shrink-0 border-b px-4 py-3" style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-1)' }}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" style={{ color: '#a78bfa' }} />
              <span className="text-xs font-medium" style={{ color: '#a78bfa' }}>{genStage}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {Math.round(genProgress * 100)}%
              </span>
              <button onClick={cancelGenerate} className="text-[10px] px-2 py-0.5 rounded border transition-colors"
                style={{ borderColor: 'var(--border-1)', color: 'var(--text-muted)' }}>
                Cancel
              </button>
            </div>
          </div>
          <div className="h-1 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--surface-3)' }}>
            <div className="h-full rounded-full transition-all duration-300" style={{ width: `${genProgress * 100}%`, backgroundColor: '#a78bfa' }} />
          </div>
          {genLog.length > 0 && (
            <div className="mt-2 max-h-[100px] overflow-y-auto rounded-lg border p-2 font-mono text-[10px] space-y-0.5"
              style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)', color: 'var(--text-muted)' }}>
              {genLog.slice(-20).map((line, i) => <div key={i}>{line}</div>)}
            </div>
          )}
        </div>
      )}

      {/* Trace viewer panel */}
      {showTraces && traceData && (
        <div className="shrink-0 border-b px-4 py-3 max-h-[50vh] overflow-y-auto" style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-1)' }}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Cpu size={12} style={{ color: '#a78bfa' }} />
              <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>Pipeline Traceability</span>
            </div>
            <button onClick={() => setShowTraces(false)} style={{ color: 'var(--text-muted)' }}>
              <X size={12} />
            </button>
          </div>
          <TraceViewer
            traceability={traceData.traceability}
            webSearch={traceData.web_search}
          />
        </div>
      )}

      {/* Pack summary */}
      {packData && <PackSummary readme={packData.readme} />}

      {/* Row count bar */}
      {packData && !loadingData && (
        <div className="shrink-0 border-b px-4 py-2 flex items-center gap-3"
          style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-1)' }}>
          <FileSpreadsheet size={10} style={{ color: 'var(--text-faint)' }} />
          <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
            {filteredPosts.length}{filteredPosts.length !== packData.posts.length ? ` of ${packData.posts.length}` : ''} posts
            · {packData.headers.length} columns
            {editCount > 0 && ` · ${editCount} unsaved edit${editCount !== 1 ? 's' : ''}`}
            · click row to expand
          </span>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 overflow-hidden relative">
        {loadingData && (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
          </div>
        )}

        {!loadingData && !loadingPacks && packs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <FileSpreadsheet size={28} className="mb-4" style={{ color: 'var(--text-faint)' }} />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No post packs yet for {displayName}.</p>
            <p className="mt-1.5 text-xs" style={{ color: 'var(--text-faint)' }}>
              Drop Excel files into{' '}
              <code className="rounded px-1.5 py-0.5 text-[11px] font-mono"
                style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}>
                data/founders/{slug}/post-data/
              </code>
            </p>
          </div>
        )}

        {/* Post customizer — above table */}
        {custVariant && packData && (
          <div className="shrink-0 border-b px-4 py-3 space-y-2" style={{ borderColor: 'var(--border-2)' }}>
            {!custApiKey && (
              <div className="flex items-center gap-2 rounded-lg border px-3 py-2"
                style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-2)' }}>
                <span className="text-[11px] shrink-0" style={{ color: 'var(--text-muted)' }}>API Key:</span>
                <input
                  type="password"
                  value={custApiKey}
                  onChange={e => { setCustApiKey(e.target.value); localStorage.setItem('asksharath_api_key', e.target.value) }}
                  placeholder="sk-ant-..."
                  className="flex-1 rounded border px-2 py-1 text-[12px] focus:outline-none"
                  style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-3)', color: 'var(--text-primary)' }}
                />
              </div>
            )}
            <PostCustomizer
              variant={custVariant}
              founderSlug={slug || ''}
              apiKey={custApiKey}
              effort={effort}
              voiceMarkers={packData.readme?.['Voice Markers'] || ''}
              onClose={() => { setCustVariant(null); setCustPost('') }}
              onPostReady={setCustPost}
            />
          </div>
        )}

        {!loadingData && packData && (
          <PostTable
            posts={filteredPosts}
            headers={packData.headers}
            selectedPost={selectedPost}
            onSelectRow={setSelectedPost}
            visibleGroups={visibleGroups}
            edits={edits}
            onEdit={handleEdit}
          />
        )}
      </div>

      {/* Customize section — variant selection cards (inline, below table) */}
      {selectedPost && packData && !custVariant && (
        <div className="shrink-0 border-t px-4 py-3" style={{ borderColor: 'var(--border-2)' }}>
          <CustomizeSection
            post={selectedPost}
            onSelectVariant={(letter, opener, body) => {
              setCustVariant({ letter, opener, originalBody: body })
              setCustPost('')
            }}
            onShowDetails={() => setShowDetail(true)}
            onClose={() => setSelectedPost(null)}
          />
        </div>
      )}

      {/* Detail panel — opened via "Full Details" button */}
      {showDetail && selectedPost && packData && (
        <DetailPanel
          post={selectedPost}
          headers={packData.headers}
          edits={edits}
          onEdit={handleEdit}
          onClose={() => setShowDetail(false)}
          onSelectVariant={(letter, opener, body) => {
            setCustVariant({ letter, opener, originalBody: body })
            setCustPost('')
            setShowDetail(false)
          }}
        />
      )}

      {/* Corner chatbot for iterative edits */}
      {custVariant && custPost && (
        <CornerChatbot
          currentPost={custPost}
          onPostUpdate={setCustPost}
          founderSlug={slug || ''}
          apiKey={custApiKey}
          effort={effort}
          voiceMarkers={packData?.readme?.['Voice Markers'] || ''}
        />
      )}
    </div>
  )
}
