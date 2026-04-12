import { Check } from 'lucide-react'
import clsx from 'clsx'

type StepState = 'pending' | 'active' | 'completed'

const STEPS = [
  { key: 'generate', label: 'Generate' },
  { key: 'vote', label: 'Audience Vote' },
  { key: 'refine', label: 'Refine' },
  { key: 'massacre', label: 'Opening Massacre' },
  { key: 'humanize', label: 'Humanize & Score' },
] as const

interface Props {
  stepStates: Record<string, StepState>
}

export default function PipelineStepper({ stepStates }: Props) {
  return (
    <div className="flex items-center justify-between">
      {STEPS.map((step, i) => {
        const state = stepStates[step.key] ?? 'pending'
        return (
          <div key={step.key} className="flex flex-1 items-center">
            {/* Step circle */}
            <div className="flex flex-col items-center gap-1">
              <div
                className={clsx(
                  'flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold transition-all',
                  state === 'completed' && 'bg-white/20 text-white',
                  state === 'active' &&
                    'bg-white text-black ring-4 ring-white/30 animate-pulse',
                  state === 'pending' &&
                    'border-2 border-gray-700 text-gray-500',
                )}
              >
                {state === 'completed' ? (
                  <Check size={16} />
                ) : (
                  i + 1
                )}
              </div>
              <span
                className={clsx(
                  'text-xs font-medium',
                  state === 'active' ? 'text-white' :
                  state === 'completed' ? 'text-white' :
                  'text-gray-500',
                )}
              >
                {step.label}
              </span>
            </div>

            {/* Connector line */}
            {i < STEPS.length - 1 && (
              <div
                className={clsx(
                  'mx-2 h-0.5 flex-1',
                  state === 'completed' ? 'bg-white/20' : 'bg-gray-700',
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
