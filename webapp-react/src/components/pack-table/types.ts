export interface ColDef {
  key: string
  label: string
  group: string
  variantLetter?: 'A' | 'B' | 'C' | 'D' | 'E'
  width: number
  sticky?: boolean
  render?: 'status' | 'status-editable' | 'type' | 'variant-badge' | 'score-dots' | 'mono'
  truncate?: boolean
}

export const VARIANT_LETTERS = ['A', 'B', 'C', 'D', 'E'] as const

export const VARIANT_ACCENT: Record<string, { header: string; cell: string; badge: string; light: string }> = {
  A: { header: 'bg-violet-950/50 text-violet-300/80', cell: 'bg-violet-950/30', badge: 'bg-violet-400 text-black', light: 'bg-violet-100 border-violet-300' },
  B: { header: 'bg-sky-950/50 text-sky-300/80',       cell: 'bg-sky-950/30',    badge: 'bg-sky-400 text-black',    light: 'bg-sky-100 border-sky-300' },
  C: { header: 'bg-emerald-950/50 text-emerald-300/80', cell: 'bg-emerald-950/30', badge: 'bg-emerald-400 text-black', light: 'bg-emerald-100 border-emerald-300' },
  D: { header: 'bg-amber-950/50 text-amber-300/80',   cell: 'bg-amber-950/30',  badge: 'bg-amber-400 text-black',  light: 'bg-amber-100 border-amber-300' },
  E: { header: 'bg-rose-950/50 text-rose-300/80',     cell: 'bg-rose-950/30',   badge: 'bg-rose-400 text-black',   light: 'bg-rose-100 border-rose-300' },
}

export const ALL_GROUPS = ['Core', 'Content', 'Source', 'Analysis', 'Variant A', 'Variant B', 'Variant C', 'Variant D', 'Variant E', 'Extra']

export interface PackData {
  readme: Record<string, string>
  headers: string[]
  posts: Record<string, any>[]
}
