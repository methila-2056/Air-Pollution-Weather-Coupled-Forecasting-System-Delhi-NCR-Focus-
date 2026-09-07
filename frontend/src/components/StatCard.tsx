interface StatCardProps {
  label: string
  value: string | number | null | undefined
  sub?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
}

const toneClasses: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'text-white',
  good: 'text-green-400',
  warn: 'text-orange-400',
  bad: 'text-red-400',
}

export default function StatCard({ label, value, sub, tone = 'default' }: StatCardProps) {
  return (
    <div className="card">
      <p className="card-header">{label}</p>
      <p className={`stat-value ${toneClasses[tone]}`}>{value ?? '--'}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}