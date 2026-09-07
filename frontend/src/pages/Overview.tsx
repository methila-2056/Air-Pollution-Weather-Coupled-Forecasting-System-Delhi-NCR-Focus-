import { useState, useEffect } from 'react'
import { getStations, getCurrentAQI, getForecast, getWeather, getInversion, getFireActivity, getPlumeRisk, getExplanation } from '../api/client'
import AQICard from '../components/AQICard'
import ForecastChart from '../components/ForecastChart'
import InversionPanel from '../components/InversionPanel'
import StubblePlume from '../components/StubblePlume'
import ExplainabilityPanel from '../components/ExplainabilityPanel'
import type { Station, CurrentAQI, ForecastPoint, WeatherData, InversionData, FireActivity, PlumeRisk, Explanation, Alert } from '../types'

export default function Overview() {
  const [stations, setStations] = useState<Station[]>([])
  const [selectedStation, setSelectedStation] = useState('Anand Vihar')
  const [aqi, setAqi] = useState<CurrentAQI | null>(null)
  const [forecast, setForecast] = useState<ForecastPoint[]>([])
  const [weather, setWeather] = useState<WeatherData | null>(null)
  const [inversion, setInversion] = useState<InversionData | null>(null)
  const [fire, setFire] = useState<FireActivity | null>(null)
  const [plumeRisk, setPlumeRisk] = useState<PlumeRisk | null>(null)
  const [explanation, setExplanation] = useState<Explanation | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getStations().then(res => setStations(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getCurrentAQI(selectedStation).then(r => setAqi(r.data)).catch(() => {}),
      getForecast(selectedStation).then(r => setForecast(r.data)).catch(() => {}),
      getWeather(selectedStation).then(r => setWeather(r.data)).catch(() => {}),
      getInversion(selectedStation).then(r => setInversion(r.data)).catch(() => {}),
      getFireActivity().then(r => setFire(r.data)).catch(() => {}),
      getPlumeRisk().then(r => setPlumeRisk(r.data)).catch(() => {}),
      getExplanation(selectedStation).then(r => setExplanation(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [selectedStation])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Delhi NCR Air Intelligence</h1>
          <p className="text-gray-400 text-sm">Real-time monitoring & 72-hour forecasting</p>
        </div>
        <select
          value={selectedStation}
          onChange={e => setSelectedStation(e.target.value)}
          className="bg-navy-800 border border-navy-700 rounded-lg px-4 py-2 text-sm"
        >
          {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
          {!stations.length && <option>Anand Vihar</option>}
        </select>
      </div>

      {loading && <div className="text-center py-12 text-gray-400">Loading data...</div>}

      <div className="grid grid-cols-4 gap-4">
        <AQICard label="AQI" value={aqi?.aqi} />
        <AQICard label="PM2.5" value={aqi?.pm25} unit="μg/m³" />
        <AQICard label="PM10" value={aqi?.pm10} unit="μg/m³" />
        <AQICard label="Category" value={aqi?.aqi_category ?? '--'} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <AQICard label="Temperature" value={weather?.temperature} unit="°C" />
        <AQICard label="Humidity" value={weather?.humidity} unit="%" />
        <AQICard label="Wind Speed" value={weather?.wind_speed} unit="m/s" />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-lg font-semibold mb-3">72-Hour AQI Forecast</h2>
          <ForecastChart data={forecast} pollutant="aqi_pred" color="#3b82f6" />
        </div>
        <InversionPanel data={inversion} />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <StubblePlume data={plumeRisk} />
        <ExplainabilityPanel data={explanation} />
      </div>
    </div>
  )
}
