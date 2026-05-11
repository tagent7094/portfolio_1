import type { ColDef } from './types'
import { VARIANT_LETTERS, VARIANT_ACCENT } from './types'

export function s(val: any): string {
  return val === null || val === undefined ? '' : String(val)
}

export function statusColor(value: string): string {
  const v = value.toLowerCase()
  if (v.includes('approved') || v.includes('done') || v.includes('final'))
    return 'bg-emerald-950/60 text-emerald-400 border-emerald-800/40'
  if (v.includes('pending') || v.includes('review'))
    return 'bg-amber-950/60 text-amber-400 border-amber-800/40'
  if (v.includes('reject') || v.includes('no'))
    return 'bg-red-950/60 text-red-400 border-red-800/40'
  if (v.includes('draft') || v.includes('wip'))
    return 'bg-sky-950/60 text-sky-400 border-sky-800/40'
  return 'bg-white/[0.04] text-white/45 border-white/[0.08]'
}

export function groupHeaderClass(group: string): string {
  for (const v of VARIANT_LETTERS) {
    if (group === `Variant ${v}`) return VARIANT_ACCENT[v].header
  }
  return 'bg-[#0d0d0d] text-white/40'
}

export function buildColDefs(headers: string[]): ColDef[] {
  function res(...candidates: string[]): string | null {
    for (const c of candidates) { if (headers.includes(c)) return c }
    return null
  }
  const statusCols = headers.filter(h => h.startsWith('Status')).map(sh => ({
    key: sh,
    label: sh.replace(/^Status\s*/, '').replace(/[()]/g, '').trim() || sh,
    group: 'Core',
    width: 130,
    render: 'status-editable' as const,
  }))

  function col(
    key: string | null,
    label: string,
    group: string,
    width: number,
    extra?: Partial<ColDef>,
  ): ColDef | null {
    if (!key) return null
    return { key, label, group, width, ...extra }
  }

  const structured: (ColDef | null)[] = [
    { key: 'Row #', label: 'Row #', group: 'Core', width: 52, sticky: true, render: 'mono' },
    col(res('File'),           'File',         'Core',     80,  { truncate: true }),
    col(res('Source #'),       'Src #',        'Core',     56,  { render: 'mono' }),
    col(res('Type'),           'Type',         'Core',     72,  { render: 'type' }),
    ...statusCols,
    col(res('Post Topic (derived from body)', 'Post Topic', 'Topic'), 'Topic', 'Content', 160, { truncate: true }),
    col(res('Domain'),         'Domain',       'Content', 100, { truncate: true }),
    col(res('Kind'),           'Kind',         'Content',  80),
    col(res('Final Post'),     'Final Post',   'Content', 220, { truncate: true }),
    col(res('Finalized Post'), 'Finalized',    'Content', 220, { truncate: true }),
    col(res('Current Score (pts)', 'Score'), 'Score', 'Content', 70),
    col(res('Source Quote'),   'Source Quote', 'Source',  200, { truncate: true }),
    col(res('Mechanic'),       'Mechanic',     'Source',  120, { truncate: true }),
    col(res('Original Opening'), 'Orig. Opening', 'Source', 180, { truncate: true }),
    col(res('Original Type'),  'Orig. Type',   'Source',  100),
    col(res("Buried Gold (from this post's paras 2-4)", 'Buried Gold'), 'Buried Gold', 'Analysis', 200, { truncate: true }),
    col(res('Weakness'),       'Weakness',     'Analysis', 180, { truncate: true }),
    col(res('Recommended'),    'Rec.',         'Analysis',  72, { render: 'variant-badge' }),
    col(res('Why'),            'Why',          'Analysis', 200, { truncate: true }),
    ...VARIANT_LETTERS.flatMap(v => [
      col(res(`${v}, Opening`,      `${v} - Opening`,      `Variant ${v} Opening`),      'Opening',    `Variant ${v}`, 200, { variantLetter: v, truncate: true }),
      col(res(`${v}, Rewrite Type`, `${v} - Rewrite Type`, `Variant ${v} Rewrite Type`), 'Type',       `Variant ${v}`, 120, { variantLetter: v }),
      col(res(`${v}, Key Change`,   `${v} - Key Change`,   `Variant ${v} Key Change`),   'Key Change', `Variant ${v}`, 160, { variantLetter: v, truncate: true }),
      col(res(`${v}, Expected Lift`,`${v} - Expected Lift`, `Variant ${v} Expected Lift`),'Lift',       `Variant ${v}`,  72, { variantLetter: v, render: 'score-dots' }),
    ] as (ColDef | null)[]),
  ]

  const definedCols = structured.filter((c): c is ColDef => c !== null)

  const mappedKeys = new Set(definedCols.map(c => c.key))
  const extraCols: ColDef[] = headers
    .filter(h => !mappedKeys.has(h))
    .map(h => ({ key: h, label: h, group: 'Extra', width: 160, truncate: true }))

  return [...definedCols, ...extraCols]
}
