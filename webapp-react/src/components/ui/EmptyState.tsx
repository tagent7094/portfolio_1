import clsx from 'clsx'
import type { ReactNode } from 'react'

interface Props {
  icon?: ReactNode
  title?: string
  description?: string
  action?: ReactNode
  className?: string
}

export default function EmptyState({ icon, title, description, action, className }: Props) {
  return (
    <div className={clsx('flex flex-col items-center justify-center gap-3 py-16 text-center', className)}>
      {icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--surface-3)] text-[var(--text-muted)]">
          {icon}
        </div>
      )}
      {title && <p className="text-[14px] font-semibold text-[var(--text-secondary)]">{title}</p>}
      {description && <p className="max-w-xs text-[12px] text-[var(--text-muted)]">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
