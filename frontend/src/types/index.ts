export interface Station {
  id: number
  name: string
  latitude: number
  longitude: number
  city: string
}

export interface CurrentAQI {
  station: string
  timestamp: string
  pm25: number | null
  pm10: number | null
  o3: number | null
  no2: number | null
  so2: number | null
  co: number | null
  aqi: number | null
  aqi_category: string
  dominant_pollutant: string
}

export interface ForecastPoint {
  timestamp: string
  horizon_hours: number
  pm25_pred: number | null
  pm10_pred: number | null
  o3_pred: number | null
  no2_pred: number | null
  aqi_pred: number | null
  aqi_category: string
}

export interface WeatherData {
  station: string
  timestamp: string
  temperature: number | null
  humidity: number | null
  pressure_msl: number | null
  surface_pressure: number | null
  wind_speed: number | null
  wind_direction: number | null
  precipitation: number | null
  cloud_cover: number | null
  pbl_height: number | null
}

export interface InversionData {
  station: string
  timestamp: string
  pbl_height: number | null
  inversion_detected: boolean
  inversion_strength: string
  trapping_risk: string
}

export interface FireActivity {
  total_fires: number
  high_confidence_fires: number
  mean_frp: number
  region: string
  date: string
}

export interface PlumeRisk {
  risk_level: string
  risk_score: number
  fire_count: number
  transport_direction: string
  wind_speed: number
  distance_nearest_fire: number
  confidence: number
  factors: string[]
}

export interface Explanation {
  station: string
  timestamp: string
  prediction: Record<string, any>
  top_features: Array<{
    feature: string
    importance: number
    direction: string
    description: string
  }>
  natural_language: string[]
}

export interface Alert {
  id: number
  station: string
  alert_level: string
  title: string
  description: string
  forecast_horizon_hours: number | null
  factors: string | null
  recommendation: string | null
  created_at: string
}

export interface ModelMetric {
  model_name: string
  pollutant: string
  horizon_hours: number
  mae: number | null
  rmse: number | null
  r2: number | null
  mape: number | null
  test_period_start: string | null
  test_period_end: string | null
}
