interface StatCardProps {
  label: string
  value: string | number | null | undefined
  sub?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
}

const toneClasses: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'text-slate-900',
  good: 'text-green-700',
  warn: 'text-amber-700',
  bad: 'text-red-700',
}

export default function StatCard({ label, value, sub, tone = 'default' }: StatCardProps) {
  return (
    <div className="card">
      <p className="card-header">{label}</p>
      <p className={`stat-value ${toneClasses[tone]}`}>{value ?? '--'}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  )
}