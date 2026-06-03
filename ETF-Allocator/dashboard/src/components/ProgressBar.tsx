import { InfoTip } from './InfoTip';

interface ProgressBarProps {
  value: number
  max?: number
  color?: 'auto' | 'safe' | 'warning' | 'danger' | 'primary'
  height?: number
  label?: string
  showPercent?: boolean
  info?: string
}

function getColor(value: number, max: number): string {
  const ratio = value / max
  if (ratio >= 1) return '#EF4444'
  if (ratio >= 0.85) return '#F59E0B'
  return '#10B981'
}

const COLOR_MAP = {
  safe: '#10B981',
  warning: '#F59E0B',
  danger: '#EF4444',
  primary: '#7C3AED',
}

export default function ProgressBar({
  value, max = 1, color = 'auto', height = 8, label, showPercent = false, info,
}: ProgressBarProps) {
  const pct = Math.min((value / max) * 100, 100)
  const fillColor = color === 'auto' ? getColor(value, max) : COLOR_MAP[color]

  return (
    <div className="w-full">
      {(label || showPercent) && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-[#6B7280] flex items-center gap-0.5">
            {label}
            {info && <InfoTip text={info} />}
          </span>
          {showPercent && (
            <span className="nums text-xs font-medium text-[#1F2937]">
              {pct.toFixed(1)}%
            </span>
          )}
        </div>
      )}
      <div className="w-full rounded-full bg-gray-100/80 overflow-hidden" style={{ height }}>
        <div className="rounded-full transition-all duration-500 ease-out"
          style={{ width: `${pct}%`, height: '100%', backgroundColor: fillColor }} />
      </div>
    </div>
  )
}
