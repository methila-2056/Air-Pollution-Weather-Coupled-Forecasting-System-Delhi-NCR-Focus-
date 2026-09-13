import { MapContainer, TileLayer, Popup, CircleMarker, Polyline } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { Station, FireHotspot, PollutionReading } from '../types'

interface WindVector {
  lat: number
  lon: number
  direction_deg: number | null
  speed: number | null
}

interface Props {
  stations: Station[]
  onSelectStation?: (name: string) => void
  fires?: FireHotspot[]
  pollution?: PollutionReading[]
  wind?: WindVector[]
}

function frpColor(frp?: number | null): string {
  const v = frp ?? 1
  if (v >= 100) return '#ff0000'
  if (v >= 50) return '#ff7f00'
  if (v >= 20) return '#ffd700'
  return '#ff4444'
}

function frpRadius(frp?: number | null): number {
  const v = frp ?? 1
  return Math.min(14, Math.max(3, 2 + Math.log10(1 + v) * 2.5))
}

function aqiColor(aqi?: number | null): string {
  const v = aqi ?? 0
  if (v <= 50) return '#00e400'
  if (v <= 100) return '#ffff00'
  if (v <= 200) return '#ff7e00'
  if (v <= 300) return '#ff0000'
  return '#7e0023'
}

function windArrowPoints(w: WindVector): [number, number][] {
  // Meteorological direction: angle the wind blows FROM (0=N, clockwise).
  // The arrow shows the flow direction (TO = FROM + 180).
  const speed = w.speed ?? 1
  const deg = w.direction_deg ?? 0
  const towardRad = ((deg + 180) % 360) * (Math.PI / 180)
  const len = Math.min(40, 6 + speed * 3)
  const latScale = len / 111320
  const lonScale = len / (111320 * Math.cos((w.lat * Math.PI) / 180))
  const tip: [number, number] = [w.lat + latScale * Math.cos(towardRad), w.lon + lonScale * Math.sin(towardRad)]
  const back: [number, number] = [w.lat - latScale * 0.45 * Math.cos(towardRad), w.lon - lonScale * 0.45 * Math.sin(towardRad)]
  const headRad = (Math.PI * 5) / 6
  const headL = len * 0.3
  const left: [number, number] = [
    tip[0] + headL * Math.cos(towardRad + headRad) * (latScale / lonScale || 1),
    tip[1] + headL * Math.sin(towardRad + headRad),
  ]
  const right: [number, number] = [
    tip[0] + headL * Math.cos(towardRad - headRad) * (latScale / lonScale || 1),
    tip[1] + headL * Math.sin(towardRad - headRad),
  ]
  return [back, tip, left, tip, right]
}

export default function StationMap({ stations, onSelectStation, fires = [], pollution = [], wind = [] }: Props) {
  const latest = new Map<number, PollutionReading>()
  pollution.forEach(p => {
    if (!latest.has(p.station_id)) latest.set(p.station_id, p)
  })

  return (
    <MapContainer center={[28.6139, 77.2090]} zoom={10} className="h-96 rounded-xl z-0">
      <TileLayer
        attribution='&copy; OpenStreetMap contributors &copy; CARTO'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {fires.map((f, i) => (
        <CircleMarker
          key={`${f.lat}-${f.lon}-${i}`}
          center={[f.lat, f.lon]}
          pathOptions={{ color: frpColor(f.frp), fillColor: frpColor(f.frp), fillOpacity: 0.55 }}
          radius={frpRadius(f.frp)}
        >
          <Popup>
            <div className="text-xs">
              <p className="font-bold">FIRMS Hotspot</p>
              <p>FRP: {f.frp?.toFixed(1) ?? '--'} MW</p>
              <p>Confidence: {f.confidence ?? '--'}</p>
              {f.acq_date && <p>{String(f.acq_date).slice(0, 16)}</p>}
            </div>
          </Popup>
        </CircleMarker>
      ))}
      {wind.map((w, i) => (
        <Polyline
          key={`wind-${i}`}
          positions={windArrowPoints(w)}
          pathOptions={{ color: '#06b6d4', weight: 2, opacity: 0.8 }}
        />
      ))}
      {stations.map(s => {
        const reading = latest.get(s.id)
        return (
          <CircleMarker
            key={s.id}
            center={[s.latitude, s.longitude]}
            pathOptions={{ color: aqiColor(reading?.aqi), fillColor: aqiColor(reading?.aqi), fillOpacity: 0.85 }}
            radius={9}
            eventHandlers={{ click: () => onSelectStation?.(s.name) }}
          >
            <Popup>
              <div className="text-sm">
                <p className="font-bold">{s.name}</p>
                <p className="text-gray-500">{s.city}{s.state ? `, ${s.state}` : ''}</p>
                {reading ? (
                  <>
                    <p>AQI: {reading.aqi?.toFixed(0) ?? '--'}</p>
                    <p>PM2.5: {reading.pm25?.toFixed(1) ?? '--'} μg/m³</p>
                    <p>{reading.timestamp.slice(0, 16)}</p>
                  </>
                ) : (
                  <p className="text-gray-400">No pollution reading yet</p>
                )}
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}