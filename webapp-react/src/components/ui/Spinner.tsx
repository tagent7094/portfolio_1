import { Loader2 } from 'lucide-react'
import clsx from 'clsx'

interface Props { size?: number; className?: string; fullPage?: boolean }

export default function Spinner({ size = 20, className, fullPage }: Props) {
  const spinner = <Loader2 size={size} className={clsx('animate-spin text-[var(--text-muted)]', className)} />
  if (fullPage) {
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center">
        {spinner}
      </div>
    )
  }
  return spinner
}
