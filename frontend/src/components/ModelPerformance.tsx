import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { ModelMetric } from '../types'

export default function ModelPerformance({ metrics }: { metrics: ModelMetric[] }) {
  if (!metrics.length) return <div className="card"><p className="text-gray-400">No model metrics available. Train the model first.</p></div>

  const chartData = metrics.filter(m => m.model_name === 'xgboost').map(m => ({
    name: `${m.pollutant.toUpperCase()} +${m.horizon_hours}h`,
    MAE: m.mae ? +m.mae.toFixed(2) : 0,
    RMSE: m.rmse ? +m.rmse.toFixed(2) : 0,
  }))

  return (
    <div className="card">
      <h3 className="card-header">XGBoost Model Performance</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a1f52" />
          <XAxis dataKey="name" stroke="#6b7280" fontSize={11} />
          <YAxis stroke="#6b7280" fontSize={12} />
          <Tooltip contentStyle={{ backgroundColor: '#111640', border: '1px solid #252b68', borderRadius: 8 }} />
          <Legend />
          <Bar dataKey="MAE" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="RMSE" fill="#06b6d4" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-navy-700">
              <th className="text-left py-2">Model</th>
              <th className="text-left py-2">Pollutant</th>
              <th className="text-left py-2">Horizon</th>
              <th className="text-right py-2">MAE</th>
              <th className="text-right py-2">RMSE</th>
              <th className="text-right py-2">R²</th>
              <th className="text-right py-2">MAPE</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m, i) => (
              <tr key={i} className="border-b border-navy-700/50">
                <td className="py-2">{m.model_name}</td>
                <td className="py-2">{m.pollutant.toUpperCase()}</td>
                <td className="py-2">+{m.horizon_hours}h</td>
                <td className="text-right py-2">{m.mae?.toFixed(2) ?? '--'}</td>
                <td className="text-right py-2">{m.rmse?.toFixed(2) ?? '--'}</td>
                <td className="text-right py-2">{m.r2?.toFixed(3) ?? '--'}</td>
                <td className="text-right py-2">{m.mape?.toFixed(1) ?? '--'}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
