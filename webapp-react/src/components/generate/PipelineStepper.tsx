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
                  state === 'completed' && 'bg-green-600 text-white',
                  state === 'active' &&
                    'bg-indigo-600 text-white ring-4 ring-indigo-500/30 animate-pulse',
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
                  state === 'active' ? 'text-indigo-400' :
                  state === 'completed' ? 'text-green-400' :
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
                  state === 'completed' ? 'bg-green-600' : 'bg-gray-700',
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
