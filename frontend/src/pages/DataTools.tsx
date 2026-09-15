import { useEffect, useRef, useState } from 'react'
import {
  getStations,
  getForecastExportUrl,
  getWeatherExportUrl,
  getPollutionExportUrl,
  importWeatherCsv,
  importPollutionCsv,
} from '../api/client'
import PageHeader from '../components/PageHeader'
import type { Station, DataImportSummary } from '../types'

const WINDOWS = [24, 72, 168, 336]

function ExportButton({ href, label, hint }: { href: string | null; label: string; hint: string }) {
  if (!href) return null
  return (
    <div className="flex flex-col gap-1">
      <a href={href} download className="btn-primary !px-4 !py-2 text-center">{label}</a>
      <span className="text-[11px] text-slate-500">{hint}</span>
    </div>
  )
}

export default function DataTools() {
  const [stations, setStations] = useState<Station[]>([])
  const [selStation, setSelStation] = useState('Anand Vihar')
  const [hours, setHours] = useState(72)

  const weatherFileRef = useRef<HTMLInputElement>(null)
  const pollutionFileRef = useRef<HTMLInputElement>(null)
  const [weatherFile, setWeatherFile] = useState<File | null>(null)
  const [pollutionFile, setPollutionFile] = useState<File | null>(null)
  const [importing, setImporting] = useState<'weather' | 'pollution' | null>(null)
  const [result, setResult] = useState<DataImportSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStations().then(r => setStations(r.data)).catch(() => {})
  }, [])

  const readAndImport = (kind: 'weather' | 'pollution', file: File) => {
    setError(null)
    setResult(null)
    setImporting(kind)
    const reader = new FileReader()
    reader.onerror = () => { setImporting(null); setError('Could not read the selected file') }
    reader.onload = () => {
      const csv = String(reader.result ?? '')
      const call = kind === 'weather' ? importWeatherCsv(csv) : importPollutionCsv(csv)
      call
        .then(r => setResult(r.data))
        .catch(e => setError(e?.response?.data?.detail ?? 'Import failed'))
        .finally(() => setImporting(null))
    }
    reader.readAsText(file)
  }

  const template = (kind: 'weather' | 'pollution') =>
    kind === 'weather'
      ? 'station,time,temperature_2m,relative_humidity_2m,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,boundary_layer_height'
      : 'station,timestamp,pm25,pm10,o3,no2,so2,co,aqi'

  const downloadTemplate = (kind: 'weather' | 'pollution') => {
    const blob = new Blob([template(kind) + '\n'], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${kind}_import_template.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const importCard = (
    kind: 'weather' | 'pollution',
    title: string,
    description: string,
    file: File | null,
    ref_: React.RefObject<HTMLInputElement>,
    onFile: (f: File | null) => void,
  ) => (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-slate-900">{title}</h3>
          <p className="mt-1 text-xs text-slate-500">{description}</p>
        </div>
        <button className="text-xs text-inst-700 hover:underline" onClick={() => downloadTemplate(kind)}>
          Download template
        </button>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <input
          ref={ref_}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={e => onFile(e.target.files?.[0] ?? null)}
        />
        <button className="btn-outline !py-2 text-sm" onClick={() => ref_.current?.click()}>
          Choose CSV
        </button>
        <span className="flex-1 truncate text-xs text-slate-500">{file ? file.name : 'no file selected'}</span>
        <button
          className="btn-primary !py-2 text-sm disabled:opacity-50"
          disabled={!file || importing !== null}
          onClick={() => file && readAndImport(kind, file)}
        >
          {importing === kind ? 'Importing…' : 'Import'}
        </button>
      </div>
      {file && (
        <p className="mt-2 text-[11px] text-slate-500">
          Headers expected: <code className="text-slate-700">{template(kind).replace(/,/g, ', ')}</code>
        </p>
      )}
    </div>
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data Import / Export"
        subtitle="Export weather, pollution or forecast series as CSV, edit them offline, and re-import. Imports are idempotent — rows keyed on (station, timestamp) are inserted or updated in place."
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Data Tools' }]}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <select value={selStation} onChange={e => setSelStation(e.target.value)} className="select" aria-label="Select station">
              {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
            </select>
            <select value={hours} onChange={e => setHours(Number(e.target.value))} className="select !w-auto" aria-label="Time window">
              {WINDOWS.map(w => <option key={w} value={w}>last {w} hours</option>)}
            </select>
          </div>
        }
      />

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-500">Export</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <ExportButton href={getWeatherExportUrl(selStation, hours)} label="Weather CSV" hint="Open-Meteo column names (station, time, temperature_2m, …)" />
          <ExportButton href={getPollutionExportUrl(selStation, hours)} label="Pollution CSV" hint="CPCB observations (station, timestamp, pm2.5, … , aqi)" />
          <ExportButton href={getForecastExportUrl(selStation, hours)} label="Forecast CSV" hint="Persisted 72-hour model forecasts" />
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-500">Import</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {importCard('weather', 'Weather observations', 'Upload a CSV in the export format above. Only curated stations are accepted.', weatherFile, weatherFileRef, setWeatherFile)}
          {importCard('pollution', 'Pollution observations', 'Upload a CSV in the export format above; an empty aqi column is recomputed from the six criteria pollutants.', pollutionFile, pollutionFileRef, setPollutionFile)}
        </div>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      {result && (
        <div className="card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="font-semibold text-slate-900">Import summary — {result.dataset}</h3>
            <div className="flex gap-2 text-xs text-slate-500">
              <span>rows {result.rows}</span>
              <span>inserted <b className="text-emerald-600">{result.inserted}</b></span>
              <span>updated <b className="text-amber-600">{result.updated}</b></span>
              <span>unchanged <b className="text-slate-900">{result.unchanged}</b></span>
            </div>
          </div>
          {result.unknown_stations.length > 0 && (
            <p className="mb-1 text-xs text-red-700">
              Skipped unknown station(s): {result.unknown_stations.join(', ')} (network is curated to the 17 sites.)
            </p>
          )}
          {result.errors.length > 0 && (
            <ul className="list-inside list-disc space-y-0.5 text-xs text-red-700">
              {result.errors.map((err, i) => <li key={i}>{err}</li>)}
            </ul>
          )}
          {result.inserted === 0 && result.updated === 0 && result.unknown_stations.length === 0 && result.errors.length === 0 && (
            <p className="text-xs text-slate-500">Nothing changed — all rows already match the database.</p>
          )}
        </div>
      )}
    </div>
  )
}