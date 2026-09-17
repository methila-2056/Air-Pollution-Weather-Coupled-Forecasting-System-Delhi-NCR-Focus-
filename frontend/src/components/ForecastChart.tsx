import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { ForecastPoint } from '../types'
import { CHART } from '../lib/theme'

interface Props {
  data: ForecastPoint[]
  pollutant?: 'pm25_pred' | 'pm10_pred' | 'o3_pred' | 'no2_pred' | 'aqi_pred'
  color?: string
  height?: number
}

export default function ForecastChart({ data, pollutant = 'aqi_pred', color = CHART.brand, height = 300 }: Props) {
  const chartData = data.map((d) => ({
    time: `+${d.horizon_hours}h`,
    value: d[pollutant],
    category: d.aqi_category,
  }))

  return (
    <div className="card">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
          <XAxis dataKey="time" stroke={CHART.axis} fontSize={12} />
          <YAxis stroke={CHART.axis} fontSize={12} />
          <Tooltip
            contentStyle={{ backgroundColor: CHART.tooltipBg, border: `1px solid ${CHART.tooltipBorder}`, borderRadius: 8 }}
            labelStyle={{ color: CHART.tooltipLabel }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}