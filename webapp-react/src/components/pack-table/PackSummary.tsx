export function PackSummary({ readme }: { readme: Record<string, string> }) {
  const primary = [
    { key: 'Posts', label: 'Total Posts' },
    { key: 'Date', label: 'Pack Date' },
    { key: 'Founder', label: 'Founder' },
    { key: 'Pack', label: 'Pack' },
  ].filter(x => readme[x.key])

  const voice = [
    { key: 'Median word count', label: 'Med. words' },
    { key: 'Tagged cast rate', label: 'Tagged cast' },
    { key: 'Hashtag rate', label: 'Hashtag rate' },
  ].filter(x => readme[x.key])

  if (primary.length === 0) return null

  return (
    <div className="shrink-0 border-b px-4 py-3"
      style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 sm:flex sm:flex-wrap sm:items-center sm:gap-8">
        {primary.map(({ key, label }) => (
          <div key={key}>
            <div className="text-[9px] uppercase tracking-widest mb-0.5" style={{ color: 'var(--text-faint)' }}>{label}</div>
            <div className="font-[var(--font-display)] text-base sm:text-xl font-bold leading-tight" style={{ color: 'var(--text-primary)' }}>{readme[key]}</div>
          </div>
        ))}
        {voice.length > 0 && (
          <>
            <div className="h-7 w-px hidden sm:block" style={{ backgroundColor: 'var(--border-1)' }} />
            {voice.map(({ key, label }) => (
              <div key={key}>
                <div className="text-[9px] uppercase tracking-widest mb-0.5" style={{ color: 'var(--text-faint)' }}>{label}</div>
                <div className="text-xs sm:text-sm" style={{ color: 'var(--text-secondary)' }}>{readme[key]}</div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
