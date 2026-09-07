import { NavLink } from 'react-router-dom'
import { LayoutDashboard, TrendingUp, Map, Wind, Flame, Brain, Bell, BarChart3, Grid3x3 } from 'lucide-react'

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/forecast', icon: TrendingUp, label: '72-Hour Forecast' },
  { to: '/map', icon: Map, label: 'NCR Map' },
  { to: '/spatial', icon: Grid3x3, label: 'Spatial Forecast' },
  { to: '/atmosphere', icon: Wind, label: 'Atmosphere' },
  { to: '/stubble', icon: Flame, label: 'Stubble Plume' },
  { to: '/explanation', icon: Brain, label: 'AI Explanation' },
  { to: '/alerts', icon: Bell, label: 'Alerts' },
  { to: '/performance', icon: BarChart3, label: 'Model Performance' },
]

export default function Sidebar() {
  return (
    <aside className="w-64 bg-navy-800 border-r border-navy-700 flex flex-col">
      <div className="p-6 border-b border-navy-700">
        <h1 className="text-xl font-bold text-white">AeroCast-NCR</h1>
        <p className="text-xs text-gray-400 mt-1">Air Intelligence Platform</p>
      </div>
      <nav className="flex-1 p-4 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-accent-blue/20 text-accent-blue'
                  : 'text-gray-400 hover:text-white hover:bg-navy-700'
              }`
            }
          >
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="p-4 border-t border-navy-700 text-xs text-gray-500">
        SIH26082 | MoES / NCMRWF
      </div>
    </aside>
  )
}
