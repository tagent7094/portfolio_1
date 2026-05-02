import clsx from 'clsx'
import type { ReactNode } from 'react'

interface Props {
  title: string
  subtitle?: string
  actions?: ReactNode
  className?: string
}

export default function PageHeader({ title, subtitle, actions, className }: Props) {
  return (
    <div className={clsx('flex items-start justify-between gap-4 pb-6', className)}>
      <div>
        <h1 className="text-[22px] font-bold leading-tight tracking-tight text-[var(--text-primary)] font-[var(--font-display)]">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
