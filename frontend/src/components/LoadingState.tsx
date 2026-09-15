interface LoadingStateProps {
  label?: string
  rows?: number
}

export default function LoadingState({ label = 'Loading…', rows = 3 }: LoadingStateProps) {
  return (
    <div className="space-y-3" role="status" aria-busy="true" aria-label={label}>
      <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${rows}, minmax(0, 1fr))` }}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="animate-pulse rounded-xl border border-slate-200 bg-white p-5">
            <div className="h-3 w-2/5 rounded bg-slate-200" />
            <div className="mt-2 h-8 w-3/5 rounded bg-slate-200" />
            <div className="mt-2 h-3 w-4/5 rounded bg-slate-100" />
          </div>
        ))}
      </div>
      <span className="sr-only">{label}</span>
    </div>
  )
}