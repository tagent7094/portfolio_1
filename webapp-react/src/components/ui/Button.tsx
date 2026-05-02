import { Loader2 } from 'lucide-react'
import clsx from 'clsx'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'xs' | 'sm' | 'md' | 'lg'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
  iconRight?: ReactNode
}

const variantCls: Record<Variant, string> = {
  primary:   'bg-white text-black hover:bg-white/90 disabled:bg-white/40',
  secondary: 'bg-[var(--surface-3)] text-[var(--text-primary)] border border-[var(--border-3)] hover:bg-[var(--surface-4)] disabled:opacity-40',
  ghost:     'text-[var(--text-secondary)] hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)] disabled:opacity-40',
  danger:    'bg-[var(--error-dim)] text-[var(--error)] border border-[var(--error)]/20 hover:bg-[var(--error)]/20 disabled:opacity-40',
}

const sizeCls: Record<Size, string> = {
  xs: 'h-7   px-2.5 text-[11px] gap-1.5 rounded-md',
  sm: 'h-8   px-3   text-[12px] gap-1.5 rounded-lg',
  md: 'h-9   px-4   text-[13px] gap-2   rounded-lg',
  lg: 'h-10  px-5   text-[14px] gap-2   rounded-xl',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  iconRight,
  children,
  className,
  disabled,
  ...props
}: Props) {
  return (
    <button
      disabled={disabled || loading}
      className={clsx(
        'inline-flex items-center justify-center font-semibold transition-all duration-150 select-none',
        'disabled:pointer-events-none',
        variantCls[variant],
        sizeCls[size],
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 size={14} className="animate-spin shrink-0" /> : icon ? <span className="shrink-0">{icon}</span> : null}
      {children && <span>{children}</span>}
      {!loading && iconRight ? <span className="shrink-0">{iconRight}</span> : null}
    </button>
  )
}
