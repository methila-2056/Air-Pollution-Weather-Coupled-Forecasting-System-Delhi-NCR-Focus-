import { Inbox } from 'lucide-react'

interface EmptyStateProps {
  title?: string
  hint?: string
}

export default function EmptyState({
  title = 'No data available',
  hint = 'Live observations for this station have not been published yet.',
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center">
      <Inbox className="h-7 w-7 text-slate-400" aria-hidden="true" />
      <p className="text-sm font-medium text-slate-600">{title}</p>
      <p className="max-w-sm text-xs leading-relaxed text-slate-500">{hint}</p>
    </div>
  )
}