import { useEffect, useState, useCallback } from 'react'
import { apiGet, apiPost, apiUpload } from '../../api/client'
import {
  Folder, File as FileIcon, ChevronRight, Upload,
  FolderPlus, Trash2, ArrowLeft, Home, RefreshCw, Save, X, Download,
} from 'lucide-react'

interface FileEntry {
  name: string
  type: 'file' | 'dir' | 'unknown'
  size: number | null
  modified: string | null
  permissions: string | null
}

interface FileContent {
  path: string
  size: number
  total_lines: number
  content: string
  is_binary: boolean
}

function formatSize(b: number | null) {
  if (b === null) return '-'
  if (b < 1024) return `${b} B`
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`
  return `${(b / 1024 ** 3).toFixed(1)} GB`
}

function formatDate(iso: string | null) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function FileManager() {
  const [cwd, setCwd] = useState('/opt/tagent')
  const [entries, setEntries] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [editFile, setEditFile] = useState<FileContent | null>(null)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)
  const loadDir = useCallback(async (path: string) => {
    setLoading(true)
    try {
      const d = await apiGet<{ path: string; entries: FileEntry[] }>(`/api/os/files?path=${encodeURIComponent(path)}`)
      setEntries(d.entries)
      setCwd(d.path)
      setEditFile(null)
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => { loadDir(cwd) }, [])

  const openFile = async (name: string) => {
    const path = `${cwd}/${name}`
    try {
      const f = await apiGet<FileContent>(`/api/os/files/read?path=${encodeURIComponent(path)}`)
      setEditFile(f)
      setEditContent(f.content)
    } catch {}
  }

  const saveFileViaFetch = async () => {
    if (!editFile) return
    setSaving(true)
    try {
      await fetch('/api/os/files/write', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: editFile.path, content: editContent }),
        credentials: 'include',
      })
    } catch {}
    setSaving(false)
  }

  const navigate = (name: string) => { loadDir(`${cwd}/${name}`) }
  const goUp = () => { const parts = cwd.split('/'); parts.pop(); loadDir(parts.join('/') || '/') }

  const createFolder = async () => {
    const name = prompt('Folder name:')
    if (!name) return
    try {
      await apiPost('/api/os/files/action', { action: 'mkdir', path: `${cwd}/${name}` })
      loadDir(cwd)
    } catch {}
  }

  const deleteEntry = async (name: string, type: string) => {
    if (!confirm(`Delete ${type} "${name}"?`)) return
    try {
      await apiPost('/api/os/files/action', { action: 'delete', path: `${cwd}/${name}` })
      loadDir(cwd)
    } catch {}
  }

  const uploadFile = async () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      try {
        await apiUpload(`/api/os/files/upload?path=${encodeURIComponent(cwd)}`, file)
        loadDir(cwd)
      } catch {}
    }
    input.click()
  }

  const downloadFile = async (name: string) => {
    try {
      const f = await apiGet<FileContent>(`/api/os/files/read?path=${encodeURIComponent(`${cwd}/${name}`)}&limit=100000`)
      const blob = new Blob([f.content], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = name
      a.click()
      URL.revokeObjectURL(url)
    } catch {}
  }

  const breadcrumbs = cwd.split('/').filter(Boolean)

  return (
    <div className="flex flex-col h-full text-sm">
      {/* Toolbar */}
      <div className="flex items-center gap-1.5 p-2 border-b border-white/[0.06]">
        <button onClick={goUp} className="p-1.5 rounded hover:bg-white/5 text-white/40"><ArrowLeft size={14} /></button>
        <button onClick={() => loadDir('/opt/tagent')} className="p-1.5 rounded hover:bg-white/5 text-white/40"><Home size={14} /></button>
        <button onClick={() => loadDir(cwd)} className="p-1.5 rounded hover:bg-white/5 text-white/40"><RefreshCw size={14} /></button>
        <div className="flex-1 flex items-center gap-1 px-2 py-1 rounded bg-white/5 font-mono text-xs text-white/50 overflow-x-auto">
          <span>/</span>
          {breadcrumbs.map((part, i) => (
            <span key={i} className="flex items-center gap-1">
              <button onClick={() => loadDir('/' + breadcrumbs.slice(0, i + 1).join('/'))} className="hover:text-white/80">{part}</button>
              {i < breadcrumbs.length - 1 && <ChevronRight size={10} className="text-white/20" />}
            </span>
          ))}
        </div>
        <button onClick={createFolder} className="p-1.5 rounded hover:bg-white/5 text-white/40" title="New Folder"><FolderPlus size={14} /></button>
        <button onClick={uploadFile} className="p-1.5 rounded hover:bg-white/5 text-white/40" title="Upload"><Upload size={14} /></button>
      </div>

      {editFile ? (
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-1.5 border-b border-white/[0.06] bg-white/[0.02]">
            <FileIcon size={13} className="text-white/30" />
            <span className="font-mono text-xs text-white/50 flex-1 truncate">{editFile.path}</span>
            <span className="text-xs text-white/20">{formatSize(editFile.size)}</span>
            <button onClick={saveFileViaFetch} disabled={saving} className="px-2 py-0.5 rounded bg-white/10 hover:bg-white/15 text-white/60 text-xs flex items-center gap-1"><Save size={11} />{saving ? 'Saving...' : 'Save'}</button>
            <button onClick={() => setEditFile(null)} className="p-1 rounded hover:bg-white/5 text-white/30"><X size={13} /></button>
          </div>
          {editFile.is_binary ? (
            <div className="flex-1 flex items-center justify-center text-white/30">Binary file — cannot edit</div>
          ) : (
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              spellCheck={false}
              className="flex-1 bg-transparent font-mono text-xs text-white/70 p-3 resize-none outline-none leading-5"
            />
          )}
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center h-full text-white/30">Loading...</div>
          ) : (
            <table className="w-full">
              <thead className="sticky top-0 bg-[#111116]">
                <tr className="text-white/40 text-xs">
                  <th className="text-left px-3 py-1.5 font-medium">Name</th>
                  <th className="text-right px-3 py-1.5 font-medium w-24">Size</th>
                  <th className="text-right px-3 py-1.5 font-medium w-36">Modified</th>
                  <th className="text-left px-3 py-1.5 font-medium w-20">Perms</th>
                  <th className="w-16"></th>
                </tr>
              </thead>
              <tbody>
                {entries.map(e => (
                  <tr key={e.name} className="border-b border-white/[0.03] hover:bg-white/[0.02] cursor-pointer" onDoubleClick={() => e.type === 'dir' ? navigate(e.name) : openFile(e.name)}>
                    <td className="px-3 py-1.5 flex items-center gap-2">
                      {e.type === 'dir' ? <Folder size={14} className="text-blue-400/70 shrink-0" /> : <FileIcon size={14} className="text-white/25 shrink-0" />}
                      <span className={e.type === 'dir' ? 'text-blue-300/80' : 'text-white/60'}>{e.name}</span>
                    </td>
                    <td className="px-3 py-1.5 text-right text-white/30 font-mono text-xs">{formatSize(e.size)}</td>
                    <td className="px-3 py-1.5 text-right text-white/30 text-xs">{formatDate(e.modified)}</td>
                    <td className="px-3 py-1.5 font-mono text-white/20 text-xs">{e.permissions}</td>
                    <td className="px-1 flex items-center gap-0.5">
                      {e.type === 'file' && <button onClick={(ev) => { ev.stopPropagation(); downloadFile(e.name) }} className="p-1 rounded hover:bg-white/5 text-white/20"><Download size={11} /></button>}
                      <button onClick={(ev) => { ev.stopPropagation(); deleteEntry(e.name, e.type) }} className="p-1 rounded hover:bg-red-500/20 text-white/20 hover:text-red-400"><Trash2 size={11} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
