import { useEffect } from 'react'
import { ChevronDown } from 'lucide-react'
import { useFounderStore } from '../../store/useFounderStore'

export default function FounderSelector() {
  const { founders, active, loading, load, switchFounder } = useFounderStore()

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="relative">
      <select
        value={active}
        onChange={(e) => switchFounder(e.target.value)}
        disabled={loading}
        className="appearance-none rounded-lg border border-gray-700 bg-gray-800 py-1.5 pl-3 pr-8 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
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
        size={14}
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-gray-400"
      />
    </div>
  )
}
