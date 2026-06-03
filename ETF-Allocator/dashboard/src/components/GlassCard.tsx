import type { ReactNode } from 'react'
import { InfoTip } from './InfoTip'

interface GlassCardProps {
  children: ReactNode
  className?: string
  title?: string
  info?: string
}

export default function GlassCard({ children, className = '', title, info }: GlassCardProps) {
  return (
    <div className={`glass-card p-6 ${className}`}>
      {title && (
        <h3 className="text-base font-semibold text-[#1F2937] mb-4 tracking-tight flex items-center gap-1">
          {title}
          {info && <InfoTip text={info} />}
        </h3>
      )}
      {children}
    </div>
  )
}
