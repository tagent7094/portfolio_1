import { useMemo, memo } from 'react'
import clsx from 'clsx'
import type { ColDef } from './types'
import { VARIANT_ACCENT } from './types'
import { s, groupHeaderClass, buildColDefs } from './helpers'
import { CellContent } from './cells'

function TableHeader({ colDefs }: { colDefs: ColDef[] }) {
  const stickyCol = colDefs.find(c => c.sticky)
  const nonSticky = colDefs.filter(c => !c.sticky)

  const groups: { label: string; count: number }[] = []
  for (const col of nonSticky) {
    const last = groups[groups.length - 1]
    if (last && last.label === col.group) last.count++
    else groups.push({ label: col.group, count: 1 })
  }

  return (
    <thead className="sticky top-0 z-20">
      <tr>
        {stickyCol && (
          <th
            rowSpan={2}
            className="sticky left-0 z-30 border-b-2 border-r px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-left align-middle whitespace-nowrap"
            style={{
              minWidth: stickyCol.width, width: stickyCol.width,
              backgroundColor: 'var(--surface-2)',
              borderColor: 'var(--border-1)',
              color: 'var(--text-muted)',
            }}
          >
            {stickyCol.label}
          </th>
        )}
        {groups.map(({ label, count }) => (
          <th
            key={label}
            colSpan={count}
            className={clsx(
              'border-b border-r px-3 py-1.5 text-[10px] font-semibold text-left whitespace-nowrap',
              groupHeaderClass(label),
            )}
            style={{ borderColor: 'var(--border-2)' }}
          >
            {label}
          </th>
        ))}
      </tr>
      <tr>
        {nonSticky.map(col => (
          <th
            key={col.key}
            style={Object.assign(
              col.truncate ? { minWidth: col.width, maxWidth: col.width, width: col.width } : { minWidth: col.width },
              { backgroundColor: 'var(--surface-2)', borderColor: 'var(--border-1)', color: 'var(--text-muted)' },
            )}
            className="border-b-2 border-r px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-left whitespace-nowrap"
          >
            {col.label}
          </th>
        ))}
      </tr>
    </thead>
  )
}

const TableRow = memo(function TableRow({
  post, colDefs, isSelected, onClick, edits, onEdit,
}: {
  post: Record<string, any>
  colDefs: ColDef[]
  isSelected: boolean
  onClick: () => void
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
}) {
  const rec = s(post['Recommended']).trim().toUpperCase()
  const rowId = s(post['Row #']) || String(Math.random())
  const stickyCol = colDefs.find(c => c.sticky)
  const nonSticky = colDefs.filter(c => !c.sticky)

  return (
    <tr
      onClick={onClick}
      className="group cursor-pointer border-b transition-colors"
      style={{
        borderColor: 'var(--border-2)',
        backgroundColor: isSelected ? 'var(--row-selected)' : undefined,
      }}
      onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.backgroundColor = 'var(--row-hover)' }}
      onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.backgroundColor = '' }}
    >
      {stickyCol && (
        <td
          className="sticky left-0 z-10 border-r px-3 py-2.5 align-middle whitespace-nowrap"
          style={{
            minWidth: stickyCol.width, width: stickyCol.width,
            backgroundColor: isSelected ? 'var(--surface-3)' : 'var(--surface-1)',
            borderColor: 'var(--border-1)',
            borderLeft: isSelected ? '2px solid var(--text-muted)' : undefined,
          }}
        >
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {s(post[stickyCol.key]) || '—'}
          </span>
        </td>
      )}

      {nonSticky.map(col => {
        const isRecCell = col.variantLetter !== undefined && col.variantLetter === rec
        return (
          <td
            key={col.key}
            style={Object.assign(
              col.truncate ? { minWidth: col.width, maxWidth: col.width, width: col.width } : { minWidth: col.width },
              { borderColor: 'var(--border-2)' },
            )}
            className={clsx(
              'border-r px-3 py-2.5 align-middle',
              isRecCell ? VARIANT_ACCENT[col.variantLetter!].cell : '',
            )}
          >
            <CellContent col={col} val={post[col.key]} rowId={rowId} edits={edits} onEdit={onEdit} />
          </td>
        )
      })}
    </tr>
  )
})

export function PostTable({
  posts, headers, selectedPost, onSelectRow, visibleGroups, edits, onEdit,
}: {
  posts: Record<string, any>[]
  headers: string[]
  selectedPost: Record<string, any> | null
  onSelectRow: (p: Record<string, any> | null) => void
  visibleGroups: Set<string>
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
}) {
  const allColDefs = useMemo(() => buildColDefs(headers), [headers])
  const colDefs = useMemo(
    () => allColDefs.filter(c => c.sticky || visibleGroups.has(c.group)),
    [allColDefs, visibleGroups],
  )

  return (
    <div className="h-full overflow-x-auto overflow-y-auto" style={{ backgroundColor: 'var(--page-bg)' }}>
      <table className="w-max border-separate border-spacing-0 text-left">
        <TableHeader colDefs={colDefs} />
        <tbody>
          {posts.map((post, i) => (
            <TableRow
              key={s(post['Row #']) || i}
              post={post}
              colDefs={colDefs}
              isSelected={selectedPost === post}
              onClick={() => onSelectRow(selectedPost === post ? null : post)}
              edits={edits}
              onEdit={onEdit}
            />
          ))}
        </tbody>
      </table>
      {posts.length === 0 && (
        <div className="flex items-center justify-center h-32 text-sm" style={{ color: 'var(--text-muted)' }}>
          No rows match your search.
        </div>
      )}
    </div>
  )
}
