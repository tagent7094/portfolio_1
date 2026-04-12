import clsx from 'clsx'

export interface CreativityValues {
  opening: number
  body: number
  closing: number
  tone: number
}

interface Props {
  values: CreativityValues
  onChange: (key: keyof CreativityValues, value: number) => void
}

const SLIDERS: { key: keyof CreativityValues; label: string }[] = [
  { key: 'opening', label: 'Opening' },
  { key: 'body', label: 'Body' },
  { key: 'closing', label: 'Closing' },
  { key: 'tone', label: 'Tone' },
]

function creativityLabel(value: number): { text: string; color: string } {
  if (value <= 20) return { text: 'Keep Original', color: 'text-white' }
  if (value <= 50) return { text: 'Adapt Voice', color: 'text-white' }
  if (value <= 80) return { text: 'Rewrite', color: 'text-white' }
  return { text: 'Full Creative', color: 'text-white/90' }
}

export default function CreativityControls({ values, onChange }: Props) {
  return (
    <div className="space-y-4">
      <h4 className="text-sm font-medium text-gray-300">Creativity Controls</h4>
      {SLIDERS.map(({ key, label }) => {
        const { text, color } = creativityLabel(values[key])
        return (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-sm text-gray-400">{label}</label>
              <span className="text-xs text-gray-500">{values[key]}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={values[key]}
              onChange={(e) => onChange(key, Number(e.target.value))}
              className="w-full accent-white"
            />
            <span className={clsx('text-xs font-medium', color)}>{text}</span>
          </div>
        )
      })}
    </div>
  )
}
