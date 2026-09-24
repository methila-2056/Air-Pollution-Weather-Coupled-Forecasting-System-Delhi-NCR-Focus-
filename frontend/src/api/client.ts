import axios, { type InternalAxiosRequestConfig } from 'axios'
import { latestForecastRun } from '../lib/forecast'
import type { Station, CurrentAQI, ForecastPoint, WeatherData, InversionData, FireActivity, FireHotspotsResponse, PlumeRisk, Explanation, ForecastExplanation, Alert, ModelMetric, CouplingData, CouplingFeaturesResponse, ForecastContextResponse, CoupledForecastResult, GridForecast, DispersionForecast, SummaryResponse, PollutionReading, PollutionIngestSummary, DataImportSummary, ModelPerformanceResponse, Pm25ForecastResponse, AtmosphereCurrentResponse, TransportRiskResponse, GrapAssessment, GrapStagesResponse, LoginResponse, AuthUser, DemoCredentials, PollutionEventsCurrent, DataQualityResponse, SystemResponse, ScenarioAnalysisRequest, ScenarioAnalysisResponse } from '../types'

const TOKEN_KEY = 'aerocast_token'
const USER_KEY = 'aerocast_user'

export const getStoredToken = () => sessionStorage.getItem(TOKEN_KEY) ?? localStorage.getItem(TOKEN_KEY)
export const getStoredUser = (): AuthUser | null => {
  const raw = sessionStorage.getItem(USER_KEY) ?? localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}
export const storeSession = (token: string, user: AuthUser) => {
  sessionStorage.setItem(TOKEN_KEY, token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}
export const clearSession = () => {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// Render free-tier instances sleep after ~15 min idle and take tens of
// seconds to wake; a page load right after a cold start must not drop every
// panel because of the client timeout.
const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

api.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Render free-tier instances scale to zero after ~15 min idle; the first
// requests after a cold start are answered with gateway 502/503/504 or a
// network timeout while the container boots (often 45-120 s). Panels fire a
// single GET on mount, so without retrying every page would surface an
// error/spinner whenever a demo restarts. Idempotent GETs (and the two pure
// compute POSTs /forecast/coupled and /scenario/analysis, which only read
// stored data and compute) are retried until the backend is awake.
const MAX_TRANSIENT_RETRIES = 8
const TRANSIENT_RETRY_DELAY_MS = 10000

const IDEMPOTENT_POST = /^\/(forecast\/coupled|scenario\/analysis)(\?|$)/

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const config = error?.config as (InternalAxiosRequestConfig & { retryCount?: number }) | undefined
    if (!config) return Promise.reject(error)
    const method = (config.method ?? 'get').toLowerCase()
    const isGet = method === 'get'
    const isIdempotentPost = method === 'post' && typeof config.url === 'string' && IDEMPOTENT_POST.test(config.url)
    if (!isGet && !isIdempotentPost) return Promise.reject(error)
    const status = error?.response?.status
    const transient = !error.response || status === 0 || status === 502 || status === 503 || status === 504
    if (!transient) return Promise.reject(error)
    const retryCount = config.retryCount ?? 0
    if (retryCount >= MAX_TRANSIENT_RETRIES) return Promise.reject(error)
    config.retryCount = retryCount + 1
    await new Promise((r) => setTimeout(r, TRANSIENT_RETRY_DELAY_MS))
    return api.request(config)
  },
)

export const login = (email: string, password: string) =>
  api.post<LoginResponse>('/auth/login', { email, password })
export const getMe = () => api.get<AuthUser>('/auth/me')
export const logout = () => api.post<AuthUser>('/auth/logout')
export const getDemoCredentials = () => api.get<DemoCredentials>('/auth/demo')

export const getStations = () => api.get<Station[]>('/stations')
export const getPollutionLatest = () => api.get<PollutionReading[]>('/pollution/latest')
export const getPollutionStations = () => api.get<Station[]>('/pollution/stations')
export const getPollutionHistory = (stationId: number, limit = 168) =>
  api.get<PollutionReading[]>(`/pollution/${stationId}/history`, { params: { limit } })
export const ingestPollution = () => api.post<PollutionIngestSummary>('/pollution/ingest')
export const getCurrentAQI = (station: string) => api.get<CurrentAQI>(`/current/${station}`)
export const getForecast = async (station: string, hours = 72) => {
  const res = await api.get<ForecastPoint[]>(`/forecast/${station}`, { params: { hours } })
  return { ...res, data: latestForecastRun(res.data) }
}
export const getNCRForecast = (hours = 72) => api.get<Record<string, ForecastPoint[]>>(`/forecast/ncr`, { params: { hours } })
export const getWeather = (station: string) => api.get<WeatherData>(`/weather/${station}`)
export const getInversion = (station: string) => api.get<InversionData>(`/inversion/${station}`)
export const getFireActivity = () => api.get<FireActivity>('/fire-activity')
export const getFireHotspots = () => api.get<FireHotspotsResponse>('/fire/hotspots')
export const getPlumeRisk = () => api.get<PlumeRisk>('/plume-risk')
export const getExplanation = (station: string) => api.get<Explanation>(`/explanation/${station}`)
export const getForecastExplanation = (forecastId: number) =>
  api.get<ForecastExplanation>(`/forecast/${forecastId}/explanation`)
export const getPm25ForecastExplanation = (station: string, horizon = 24) =>
  api.get<ForecastExplanation>('/forecast/pm25/explanation', { params: { station_name: station, horizon } })
export const getCoupling = (station: string) => api.get<CouplingData>(`/coupling/${station}`)
export const getCouplingFeatures = (station: string) => api.get<CouplingFeaturesResponse>(`/coupling/features/${station}`)
export const getForecastContext = (station: string) => api.get<ForecastContextResponse>(`/forecast/${station}/context`)
export const generateCoupledForecast = (station: string, horizons?: number[]) =>
  api.post<CoupledForecastResult>('/forecast/coupled', { station_name: station, horizons: horizons ?? [1, 6, 12, 24, 48, 72] }, { timeout: 120000 })
export const getGridForecast = (horizon = 24) => api.get<GridForecast>('/grid/forecast', { params: { horizon_hours: horizon } })
export const getDispersionForecast = (horizon = 72, startHour = 8) =>
  api.get<DispersionForecast>('/dispersion/forecast', { params: { horizon_hours: horizon, start_hour: startHour } })
export const getAlerts = () => api.get<Alert[]>('/alerts')
export const getModelMetrics = () => api.get<ModelMetric[]>('/model/metrics')
export const getModelPerformance = (target = 'pm25') =>
  api.get<ModelPerformanceResponse>('/model/performance', { params: { target } })
export const getPm25Forecast = (station: string, hours = 72) =>
  api.get<Pm25ForecastResponse>('/forecast/pm25', { params: { station_name: station, hours } })
export const getAtmosphereCurrent = (station?: string) =>
  api.get<AtmosphereCurrentResponse>('/atmosphere/current', { params: station ? { station_name: station } : {} })
export const getTransportRisk = (hours = 72) =>
  api.get<TransportRiskResponse>('/transport-risk/current', { params: { hours } })
export const getSummary = () => api.get<SummaryResponse>('/summary')
export const getEvents = (station?: string, hours = 48) =>
  api.get<PollutionEventsCurrent>('/events/current', { params: { station_name: station, hours } })
export const getDataQuality = () => api.get<DataQualityResponse>('/data-quality')
export const getSystemStatus = () => api.get<SystemResponse>('/system')
export const getGrapCurrent = () => api.get<GrapAssessment>('/grap/current')
export const getGrapStages = () => api.get<GrapStagesResponse>('/grap/stages')

export const getForecastExportUrl = (station: string, hours = 72) =>
  `/api/export/forecast.csv?station_name=${encodeURIComponent(station)}&hours=${hours}`
export const getWeatherExportUrl = (station: string, hours = 72) =>
  `/api/export/weather.csv?station_name=${encodeURIComponent(station)}&hours=${hours}`
export const getPollutionExportUrl = (station: string, hours = 72) =>
  `/api/export/pollution.csv?station_name=${encodeURIComponent(station)}&hours=${hours}`

const csvHeaders = { 'Content-Type': 'text/csv' }
export const importWeatherCsv = (csv: string) =>
  api.post<DataImportSummary>('/import/weather', csv, { headers: csvHeaders })
export const importPollutionCsv = (csv: string) =>
  api.post<DataImportSummary>('/import/pollution', csv, { headers: csvHeaders })

export const postScenarioAnalysis = (payload: ScenarioAnalysisRequest) =>
  api.post<ScenarioAnalysisResponse>('/scenario/analysis', payload, { timeout: 120000 })

// Exported for the keep-warm pinger (see ../warmup). While a browser tab is
// open the Render instance is polled so the demo never hits a cold start
// mid-session.
export { api }
