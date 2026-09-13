import axios from 'axios'
import type { Station, CurrentAQI, ForecastPoint, WeatherData, InversionData, FireActivity, FireHotspotsResponse, PlumeRisk, Explanation, ForecastExplanation, Alert, ModelMetric, CouplingData, CoupledForecastResult, GridForecast, DispersionForecast, SummaryResponse, PollutionReading, PollutionIngestSummary, ModelPerformanceResponse, Pm25ForecastResponse, AtmosphereCurrentResponse, TransportRiskResponse } from '../types'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

export const getStations = () => api.get<Station[]>('/stations')
export const getPollutionLatest = () => api.get<PollutionReading[]>('/pollution/latest')
export const getPollutionStations = () => api.get<Station[]>('/pollution/stations')
export const getPollutionHistory = (stationId: number, limit = 168) =>
  api.get<PollutionReading[]>(`/pollution/${stationId}/history`, { params: { limit } })
export const ingestPollution = () => api.post<PollutionIngestSummary>('/pollution/ingest')
export const getCurrentAQI = (station: string) => api.get<CurrentAQI>(`/current/${station}`)
export const getForecast = (station: string, hours = 72) => api.get<ForecastPoint[]>(`/forecast/${station}`, { params: { hours } })
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
export const generateCoupledForecast = (station: string, horizons?: number[]) =>
  api.post<CoupledForecastResult>('/forecast/coupled', { station_name: station, horizons: horizons ?? [1, 6, 12, 24, 48, 72] })
export const getGridForecast = (horizon = 24) => api.get<GridForecast>('/grid/forecast', { params: { horizon_hours: horizon } })
export const getDispersionForecast = (horizon = 72, startHour = 8) =>
  api.get<DispersionForecast>('/dispersion/forecast', { params: { horizon_hours: horizon, start_hour: startHour } })
export const getAlerts = () => api.get<Alert[]>('/alerts')
export const getModelMetrics = () => api.get<ModelMetric[]>('/model/metrics')
export const getModelPerformance = () => api.get<ModelPerformanceResponse>('/model/performance')
export const getPm25Forecast = (station: string, hours = 72) =>
  api.get<Pm25ForecastResponse>('/forecast/pm25', { params: { station_name: station, hours } })
export const getAtmosphereCurrent = (station?: string) =>
  api.get<AtmosphereCurrentResponse>('/atmosphere/current', { params: station ? { station_name: station } : {} })
export const getTransportRisk = (hours = 72) =>
  api.get<TransportRiskResponse>('/transport-risk/current', { params: { hours } })
export const getSummary = () => api.get<SummaryResponse>('/summary')

export const getForecastExportUrl = (station: string, hours = 72) =>
  `/api/export/forecast.csv?station_name=${encodeURIComponent(station)}&hours=${hours}`
