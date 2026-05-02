import clsx from 'clsx'
import type { HTMLAttributes } from 'react'

type Variant = 'default' | 'success' | 'warning' | 'error' | 'info' | 'accent'

interface Props extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant
  dot?: boolean
}

const cls: Record<Variant, string> = {
  default: 'bg-[var(--surface-3)] text-[var(--text-secondary)] border-[var(--border-3)]',
  success: 'bg-[var(--success-dim)] text-[var(--success)] border-[var(--success)]/20',
  warning: 'bg-[var(--warning-dim)] text-[var(--warning)] border-[var(--warning)]/20',
  error:   'bg-[var(--error-dim)]   text-[var(--error)]   border-[var(--error)]/20',
  info:    'bg-[var(--info-dim)]    text-[var(--info)]    border-[var(--info)]/20',
  accent:  'bg-white/10 text-white border-white/15',
}

const dotCls: Record<Variant, string> = {
  default: 'bg-[var(--text-muted)]',
  success: 'bg-[var(--success)]',
  warning: 'bg-[var(--warning)]',
  error:   'bg-[var(--error)]',
  info:    'bg-[var(--info)]',
  accent:  'bg-white',
}

export default function Badge({ variant = 'default', dot, className, children, ...props }: Props) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none',
        cls[variant],
        className,
      )}
      {...props}
    >
      {dot && <span className={clsx('h-1.5 w-1.5 rounded-full shrink-0', dotCls[variant])} />}
      {children}
    </span>
  )
}
