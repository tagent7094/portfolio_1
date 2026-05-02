import clsx from 'clsx'
import type { HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  raised?: boolean
}

export function Card({ raised, className, children, ...props }: CardProps) {
  return (
    <div
      className={clsx(raised ? 'card-raised' : 'card', className)}
      {...props}
    >
      {children}
    </div>
  )
}

interface SectionProps extends HTMLAttributes<HTMLDivElement> {
  border?: boolean
}

export function CardHeader({ className, border = true, children, ...props }: SectionProps) {
  return (
    <div
      className={clsx(
        'flex items-center justify-between px-5 py-4',
        border && 'border-b border-[var(--border-2)]',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardBody({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={clsx('px-5 py-4', className)} {...props}>
      {children}
    </div>
  )
}

export function CardTitle({ className, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={clsx('text-[14px] font-semibold text-[var(--text-primary)]', className)}
      {...props}
    >
      {children}
    </h3>
  )
}
