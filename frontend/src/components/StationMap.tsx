import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { Station } from '../types'

interface Props {
  stations: Station[]
  onSelectStation?: (name: string) => void
}

export default function StationMap({ stations, onSelectStation }: Props) {
  return (
    <MapContainer center={[28.6139, 77.2090]} zoom={10} className="h-96 rounded-xl z-0">
      <TileLayer
        attribution='&copy; OpenStreetMap contributors &copy; CARTO'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {stations.map(s => (
        <Marker
          key={s.id}
          position={[s.latitude, s.longitude]}
          eventHandlers={{ click: () => onSelectStation?.(s.name) }}
        >
          <Popup>
            <div className="text-sm">
              <p className="font-bold">{s.name}</p>
              <p className="text-gray-500">{s.city}</p>
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  )
}
