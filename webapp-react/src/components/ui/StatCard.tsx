import clsx from 'clsx'
import type { ReactNode } from 'react'

interface Props {
  icon: ReactNode
  label: string
  value: number | string
  className?: string
  animationDelay?: number
}

export default function StatCard({ icon, label, value, className, animationDelay }: Props) {
  return (
    <div
      className={clsx(
        'card animate-slide-up flex flex-col gap-3 p-4',
        className,
      )}
      style={animationDelay ? { animationDelay: `${animationDelay}ms` } : undefined}
    >
      <div className="flex items-center gap-2 text-[var(--text-muted)]">
        <span className="shrink-0">{icon}</span>
        <span className="text-[11px] font-semibold uppercase tracking-widest">{label}</span>
      </div>
      <p className="text-[28px] font-bold leading-none tracking-tight text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  )
}
