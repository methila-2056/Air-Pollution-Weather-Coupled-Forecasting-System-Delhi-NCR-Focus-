import type { ReactNode } from 'react'

interface KpiCardProps {
  label: string
  value: ReactNode
  unit?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
  sub?: string
}

const toneClasses: Record<NonNullable<KpiCardProps['tone']>, string> = {
  default: 'text-slate-900',
  good: 'text-green-700',
  warn: 'text-amber-700',
  bad: 'text-red-700',
}

export default function KpiCard({ label, value, unit, tone = 'default', sub }: KpiCardProps) {
  return (
    <div className="card">
      <p className="card-header">{label}</p>
      <p className={`text-2xl font-bold ${toneClasses[tone]}`}>
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-slate-400">{unit}</span>}
      </p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  )
}