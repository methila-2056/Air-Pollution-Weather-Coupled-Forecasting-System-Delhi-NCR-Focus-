import { useCallback, useEffect, useState } from 'react'
import { Lightbulb } from 'lucide-react'
import { getPm25ForecastExplanation, resilientGet } from '../api/client'
import { fmt, tsFmt } from '../lib/aqi'
import type { ForecastExplanation } from '../types'
import EmptyState from './EmptyState'

interface Props {
  station: string
}

export default function ForecastReasonPanel({ station }: Props) {
  const [data, setData] = useState<ForecastExplanation | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    setData(null)
    // The explanation endpoint is a live SHAP pass over the deployed model, not
    // a stored row — but a failed *request* used to be reported as "no stored
    // explanation yet", which is both wrong and unfalsifiable from the UI. It
    // retries through the shared warm-up gate instead, and only falls through to
    // the error state once the instance is genuinely not answering.
    resilientGet(() => getPm25ForecastExplanation(station, 24))
      .then((r) => { if (!cancelled) setData(r.data) })
      .catch(() => { if (!cancelled) setError(true) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [station, attempt])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  const positives = data?.top_positive_drivers ?? []
  const negatives = data?.top_negative_drivers ?? []

  const driverRow = (d: { feature: string; shap_value: number; share_of_abs_contributions_pct: number; description: string }, positive: boolean) => {
    const width = Math.max(4, Math.min(100, d.share_of_abs_contributions_pct))
    return (
      <div key={d.feature} className="space-y-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="truncate text-xs font-medium text-slate-700">{d.feature}</p>
          <p className={`whitespace-nowrap text-xs font-bold ${positive ? 'text-red-700' : 'text-green-700'}`}>
            {positive ? '+' : ''}{fmt(d.shap_value, 1)} μg/m³
          </p>
        </div>
        <div className="h-2 w-full rounded-full bg-slate-200">
          <div
            className={`h-2 rounded-full ${positive ? 'bg-red-600' : 'bg-green-600'}`}
            style={{ width: `${width}%` }}
          />
        </div>
        <p className="truncate text-[10px] text-slate-500" title={d.description}>{d.description}</p>
      </div>
    )
  }

  return (
    <section className="card">
      <div className="mb-3 flex items-center gap-2">
        <Lightbulb className="h-4 w-4 text-inst-700" aria-hidden="true" />
        <h2 className="text-base font-bold text-slate-900">Why this forecast</h2>
        {!loading && !error && data && (
          <span className="ml-auto rounded-full bg-inst-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-inst-800">
            SHAP · {data.explanation_method}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2" role="status" aria-label="Loading explanation">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="animate-pulse rounded-lg bg-slate-100 p-3">
              <div className="h-3 w-2/5 rounded bg-slate-200" />
              <div className="mt-2 h-2 w-3/4 rounded bg-slate-200" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate-500">
            Couldn&apos;t reach the explainability service for {station}. The forecast itself is unaffected — this
            panel only explains it.
          </p>
          <button
            type="button"
            onClick={retry}
            className="shrink-0 rounded-lg border border-inst-300 bg-white px-3 py-1.5 text-xs font-semibold text-inst-700 hover:bg-inst-50"
          >
            Retry
          </button>
        </div>
      ) : data ? (
        <>
          <p className="text-sm leading-relaxed text-slate-700">{data.summary}</p>

          <div className="mt-4 grid gap-5 md:grid-cols-2">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-red-700">Pushing PM2.5 up</p>
              <div className="space-y-3">{positives.map((d) => driverRow(d, true))}</div>
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-green-700">Pulling PM2.5 down</p>
              <div className="space-y-3">{negatives.length ? negatives.map((d) => driverRow(d, false)) : <p className="text-xs text-slate-500">No negative drivers contributed.</p>}</div>
            </div>
          </div>

          <p className="mt-4 text-[11px] text-slate-500">
            {data.explanation_method} on {tsFmt(data.data_as_of)} · base {fmt(data.base_value, 1)} μg/m³ · generated {tsFmt(data.generated_at)}
          </p>
        </>
      ) : (
        <EmptyState title="No explanation yet" hint="Train the explainability backend to see feature attribution for this station." />
      )}
    </section>
  )
}