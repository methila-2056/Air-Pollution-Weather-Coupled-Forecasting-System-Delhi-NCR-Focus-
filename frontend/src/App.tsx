import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import Forecast72h from './pages/Forecast72h'
import NCRMap from './pages/NCRMap'
import Atmosphere from './pages/Atmosphere'
import StubblePlumePage from './pages/StubblePlumePage'
import AIExplanation from './pages/AIExplanation'
import Alerts from './pages/Alerts'
import ModelPerformancePage from './pages/ModelPerformancePage'
import SpatialForecastPage from './pages/SpatialForecastPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/forecast" element={<Forecast72h />} />
        <Route path="/map" element={<NCRMap />} />
        <Route path="/atmosphere" element={<Atmosphere />} />
        <Route path="/stubble" element={<StubblePlumePage />} />
        <Route path="/explanation" element={<AIExplanation />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/performance" element={<ModelPerformancePage />} />
        <Route path="/spatial" element={<SpatialForecastPage />} />
      </Routes>
    </Layout>
  )
}
