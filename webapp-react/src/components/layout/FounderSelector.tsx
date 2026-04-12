import { useEffect } from 'react'
import { ChevronDown, Dna } from 'lucide-react'
import { useFounderStore } from '../../store/useFounderStore'

export default function FounderSelector() {
  const { founders, active, loading, load, switchFounder } = useFounderStore()

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="relative flex items-center gap-2">
      <Dna size={14} className="text-white/60" />
      <select
        value={active}
        onChange={(e) => switchFounder(e.target.value)}
        disabled={loading}
        className="appearance-none rounded-lg border border-white/10 bg-black py-1.5 pl-3 pr-8 text-[13px] font-medium text-white transition-colors focus:border-white/30 focus:outline-none disabled:opacity-50"
      >
        {founders.map((f) => (
          <option key={f.slug} value={f.slug}>
            {f.display_name}
          </option>
        ))}
        {founders.length === 0 && (
          <option value={active}>{active}</option>
        )}
      </select>
      <ChevronDown
        size={13}
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-white/50"
      />
    </div>
  )
}
