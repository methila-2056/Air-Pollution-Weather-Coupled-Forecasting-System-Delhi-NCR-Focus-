import { AlertCircle, RefreshCcw } from 'lucide-react'

interface ErrorStateProps {
  title?: string
  message?: string
  onRetry?: () => void
}

export default function ErrorState({
  title = 'Unable to load data',
  message = 'The request could not be completed. Please check your connection and try again.',
  onRetry,
}: ErrorStateProps) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
      <AlertCircle className="mx-auto h-8 w-8 text-red-500" aria-hidden="true" />
      <h3 className="mt-2 text-sm font-semibold text-red-800">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-red-700">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100"
        >
          <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
        </button>
      )}
    </div>
  )
}