export interface Station {
  id: number
  name: string
  latitude: number
  longitude: number
  city: string
  state?: string | null
}

export interface PollutionReading {
  station_id: number
  station: string
  city: string | null
  state: string | null
  timestamp: string
  pm25: number | null
  pm10: number | null
  o3: number | null
  no2: number | null
  so2: number | null
  co: number | null
  aqi: number | null
}

export interface PollutionIngestSummary {
  records_fetched: number
  observations_normalized: number
  stations_processed: number
  inserted: number
  updated: number
  skipped: number
  station_created: number
  station_updated: number
  errors: string[]
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
  so2_pred?: number | null
  co_pred?: number | null
  aqi_pred: number | null
  aqi_category: string
  coupling_stability?: number | null
}

export interface CouplingDiagnostics {
  aod_est: number
  radiation_transmittance: number
  pbl_suppression_factor: number
  corrected_pbl_height: number
  stability_coupling_index: number
  feedback_multiplier: number
}

export interface CoupledForecastPoint extends ForecastPoint {
  so2_pred: number | null
  co_pred: number | null
  coupling: CouplingDiagnostics
  pbl_effective: number
  coupling_stability: number
}

export interface CoupledForecastResult {
  station: string
  generated_at: string
  horizons: number[]
  mode: string
  coupled: CoupledForecastPoint[]
  uncoupled: ForecastPoint[]
  feedback_path: Array<{
    t_plus: number
    pm25: number
    pbl_effective: number
    stability: number
    feedback_multiplier: number
  }>
  saved_points: number
}

export interface GridCell {
  lat: number
  lon: number
  aqi: number
  aqi_category: string
}

export interface GridForecast {
  horizon_hours: number
  step_deg: number
  bounds: Record<string, number>
  wind_dir: number | null
  wind_speed: number | null
  cells: GridCell[]
  grid_size: number[]
  extent: { lats_min: number; lats_max: number; lons_min: number; lons_max: number }
}

export interface DispersionFrame {
  hour: number
  hour_of_day: number
  wind_speed: number
  wind_dir_deg: number
  pbl_height: number
  precip_mm: number
  coupling: {
    mean_pm25: number
    stability_coupling_index: number
    pbl_suppression_factor: number
    corrected_pbl_height: number
  }
  aqi_mean: number
  aqi_max: number
  cells: GridCell[]
}

export interface DispersionForecast {
  mode: string
  horizon_hours: number
  start_hour: number
  domain: Record<string, number>
  step_deg: number
  wx: { wind_speed: number; wind_direction: number; pbl_height: number; precipitation: number }
  fire_count: number
  fires: Array<{ lat: number; lon: number; frp: number; confidence: string | null; satellite: string | null }>
  dt_used: number
  steps_per_hour: number
  frames: DispersionFrame[]
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
  inversion_strength_score?: number | null
  inversion_category?: string | null
  inversion_source?: string | null
  inversion_base_pressure?: number | null
  inversion_top_pressure?: number | null
  strongest_layer_gradient?: number | null
  low_pbl_flag?: boolean | null
  pbl_category?: string | null
  dispersion_condition?: string | null
}

export interface CouplingDiagnostics {
  aod_est: number
  radiation_transmittance: number
  pbl_suppression_factor: number
  corrected_pbl_height: number
  stability_coupling_index: number
  feedback_multiplier: number
  coupling_strength: string
}

export interface CouplingData {
  station: string
  timestamp: string
  pm25: number | null
  pbl_height: number | null
  wind_speed: number | null
  diag: CouplingDiagnostics
  narrative: string[]
}

export interface FireActivity {
  total_fires: number
  high_confidence_fires: number
  mean_frp: number
  region: string
  date: string
}

export interface FireHotspot {
  lat: number
  lon: number
  frp?: number | null
  confidence?: string | null
  acq_date?: string | null
}

export interface FireHotspotsResponse {
  region: string
  hotspots: FireHotspot[]
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
  wind_alignment_pct?: number | null
  transport_time_hours?: number | null
  transport_risk?: number | null
  transport_risk_level?: string | null
  stubble_impact_score?: number | null
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

export interface ShapContribution {
  feature: string
  value: number | null
  shap_value: number
  share_of_abs_contributions_pct: number
  direction: 'positive' | 'negative' | 'zero'
  description: string
}

export interface ForecastExplanation {
  forecast_id: number
  station: string
  station_id: number
  model: string
  explanation_method: string
  horizon_hours: number
  forecast_timestamp: string
  forecast_pm25: number
  stored_pm25_pred: number | null
  base_value: number
  summary: string
  top_positive_drivers: ShapContribution[]
  top_negative_drivers: ShapContribution[]
  contributions_by_magnitude: ShapContribution[]
  n_features: number
  feature_values_used: Record<string, any> | null
  data_as_of: string
  generated_at: string
  test_metrics: Record<string, any> | null
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

export interface StationAQISummary {
  name: string
  aqi: number | null
  aqi_category: string
  dominant_pollutant: string | null
}

export interface SummaryResponse {
  generated_at: string
  stations: number
  stations_with_readings: number
  ncr_avg_aqi: number | null
  worst_station: StationAQISummary | null
  best_station: StationAQISummary | null
  active_fires_24h: number
  open_alerts: number
  models_trained: number
  forecast_coverage: {
    stations_with_forecast: number
    latest_forecast_at: string | null
  }
}

export interface ModelPerformanceSplitRange {
  start: string | null
  end: string | null
  n_rows: number
}

export interface ModelPerformanceMetrics {
  mae: number | null
  rmse: number | null
  r2: number | null
  mape?: number | null
  nmae?: number | null
  n: number
}

export interface ModelHorizonPerformance {
  horizon_hours: number
  n_train: number
  n_val: number
  n_test: number
  test_period_start: string | null
  test_period_end: string | null
  metrics: Record<string, ModelPerformanceMetrics>
}

export interface ModelPerformanceResponse {
  schema_version: number
  target: string
  model_dir: string
  data_source: string
  generated_at: string
  feature_count: number
  features: string[]
  horizons: number[]
  evaluated_models: string[]
  split_type: string
  split_ratios: number[] | null
  split_ranges: Record<string, ModelPerformanceSplitRange>
  results: ModelHorizonPerformance[]
}
