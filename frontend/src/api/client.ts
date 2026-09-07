import axios from 'axios'
import type { Station, CurrentAQI, ForecastPoint, WeatherData, InversionData, FireActivity, PlumeRisk, Explanation, Alert, ModelMetric, CouplingData, CoupledForecastResult, GridForecast, DispersionForecast } from '../types'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

export const getStations = () => api.get<Station[]>('/stations')
export const getCurrentAQI = (station: string) => api.get<CurrentAQI>(`/current/${station}`)
export const getForecast = (station: string, hours = 72) => api.get<ForecastPoint[]>(`/forecast/${station}`, { params: { hours } })
export const getNCRForecast = (hours = 72) => api.get<Record<string, ForecastPoint[]>>(`/forecast/ncr`, { params: { hours } })
export const getWeather = (station: string) => api.get<WeatherData>(`/weather/${station}`)
export const getInversion = (station: string) => api.get<InversionData>(`/inversion/${station}`)
export const getFireActivity = () => api.get<FireActivity>('/fire-activity')
export const getPlumeRisk = () => api.get<PlumeRisk>('/plume-risk')
export const getExplanation = (station: string) => api.get<Explanation>(`/explanation/${station}`)
export const getCoupling = (station: string) => api.get<CouplingData>(`/coupling/${station}`)
export const generateCoupledForecast = (station: string, horizons?: number[]) =>
  api.post<CoupledForecastResult>('/forecast/coupled', { station_name: station, horizons: horizons ?? [1, 6, 12, 24, 48, 72] })
export const getGridForecast = (horizon = 24) => api.get<GridForecast>('/grid/forecast', { params: { horizon_hours: horizon } })
export const getDispersionForecast = (horizon = 72, startHour = 8) =>
  api.get<DispersionForecast>('/dispersion/forecast', { params: { horizon_hours: horizon, start_hour: startHour } })
export const getAlerts = () => api.get<Alert[]>('/alerts')
export const getModelMetrics = () => api.get<ModelMetric[]>('/model/metrics')
