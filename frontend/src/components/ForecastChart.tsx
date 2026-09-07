import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { ForecastPoint } from '../types'

interface Props {
  data: ForecastPoint[]
  pollutant?: 'pm25_pred' | 'pm10_pred' | 'o3_pred' | 'no2_pred' | 'aqi_pred'
  color?: string
}

export default function ForecastChart({ data, pollutant = 'aqi_pred', color = '#3b82f6' }: Props) {
  const chartData = data.map(d => ({
    time: `+${d.horizon_hours}h`,
    value: d[pollutant],
    category: d.aqi_category,
  }))

  return (
    <div className="card">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a1f52" />
          <XAxis dataKey="time" stroke="#6b7280" fontSize={12} />
          <YAxis stroke="#6b7280" fontSize={12} />
          <Tooltip
            contentStyle={{ backgroundColor: '#111640', border: '1px solid #252b68', borderRadius: 8 }}
            labelStyle={{ color: '#9ca3af' }}
          />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
