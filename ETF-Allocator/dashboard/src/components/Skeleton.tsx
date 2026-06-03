interface SkeletonProps {
  className?: string
  lines?: number
  height?: number
}

export function SkeletonBox({ className = '' }: SkeletonProps) {
  return <div className={`skeleton-shimmer rounded-xl ${className}`} />
}

export function SkeletonCard({ className = '' }: SkeletonProps) {
  return (
    <div className={`glass-card p-6 ${className}`}>
      <SkeletonBox className="h-4 w-1/3 mb-5" />
      <SkeletonBox className="h-3 w-full mb-3" />
      <SkeletonBox className="h-3 w-3/4 mb-3" />
      <SkeletonBox className="h-8 w-full mb-3" />
      <SkeletonBox className="h-3 w-1/2" />
    </div>
  )
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="glass-card p-6">
      <SkeletonBox className="h-4 w-1/4 mb-5" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 mb-3">
          <SkeletonBox className="h-3 w-20 flex-shrink-0" />
          <SkeletonBox className="h-3 w-16 flex-shrink-0" />
          <SkeletonBox className="h-8 flex-1" />
          <SkeletonBox className="h-3 w-12 flex-shrink-0" />
          <SkeletonBox className="h-3 w-32 flex-shrink-0 hidden lg:block" />
        </div>
      ))}
    </div>
  )
}

export function SkeletonChart() {
  return (
    <div className="glass-card p-6">
      <SkeletonBox className="h-4 w-1/4 mb-5" />
      <div className="flex gap-2 mb-4">
        <SkeletonBox className="h-8 w-20 rounded-lg" />
        <SkeletonBox className="h-8 w-20 rounded-lg" />
        <SkeletonBox className="h-8 w-20 rounded-lg" />
        <SkeletonBox className="h-8 w-20 rounded-lg" />
        <SkeletonBox className="h-8 w-20 rounded-lg" />
      </div>
      <SkeletonBox className="h-[300px] w-full" />
    </div>
  )
}
