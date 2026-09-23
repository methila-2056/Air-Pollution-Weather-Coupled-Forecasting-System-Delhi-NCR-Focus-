// Geographic helpers for the fire-transport map layers (SIH26082).
// Pure functions mirroring ml/features/fire_impact.py on the backend: the
// estimates are transparent advective heuristics, never a plume chemistry model.

import type { FireHotspot } from '../types'

const EARTH_RADIUS_KM = 6371.0
const MAX_FIRE_DISTANCE_KM = 500.0
const UPWIND_ANGLE_DEG = 90

export interface LatLon {
  lat: number
  lon: number
}

export function haversineDistance(a: LatLon, b: LatLon): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat)
  const dLon = toRad(b.lon - a.lon)
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2
  return EARTH_RADIUS_KM * 2 * Math.asin(Math.sqrt(s))
}

// Bearing FROM point `a` TO point `b` in degrees [0, 360).
export function bearing(a: LatLon, b: LatLon): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const toDeg = (r: number) => (r * 180) / Math.PI
  const dLon = toRad(b.lon - a.lon)
  const y = Math.sin(dLon) * Math.cos(toRad(b.lat))
  const x =
    Math.cos(toRad(a.lat)) * Math.sin(toRad(b.lat)) -
    Math.sin(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.cos(dLon)
  return (toDeg(Math.atan2(y, x)) + 360) % 360
}

const lowAngle = (deg: number) => ((deg % 360) + 360) % 360

// A fire is UPWIND when it lies within 90° of the direction the wind blows FROM.
export function isUpwind(fire: LatLon, center: LatLon, windFromDeg: number | null): boolean {
  if (windFromDeg == null) return false
  const diff = Math.abs(bearing(center, fire) - lowAngle(windFromDeg))
  return Math.min(diff, 360 - diff) <= UPWIND_ANGLE_DEG
}

export interface TransportPathway {
  from: LatLon
  to: LatLon
}

// Estimated advective transport pathways: the highest-FRP fires upwind of the
// centre (within 500 km), drawn as dashed lines toward the centre. This is a
// heuristic illustration of which fire clusters the wind would carry toward
// NCR — NOT a chemical transport simulation.
export function buildTransportPathways(
  fires: FireHotspot[],
  center: LatLon,
  windFromDeg: number | null,
  windSpeedMps: number | null,
  maxPaths = 6,
): TransportPathway[] {
  if (windFromDeg == null || windSpeedMps == null) return []
  const candidates = fires
    .filter((f) => isUpwind(f, center, windFromDeg) && haversineDistance(f, center) <= MAX_FIRE_DISTANCE_KM)
    .map((f) => {
      const dist = Math.max(1, haversineDistance(f, center))
      const frp = f.frp ?? 1
      const angleDiff = Math.min(Math.abs(bearing(center, f) - lowAngle(windFromDeg)), 360)
      const alignment = Math.max(0, Math.cos((angleDiff * Math.PI) / 180))
      const proximity = Math.max(0.2, 1 - dist / MAX_FIRE_DISTANCE_KM)
      const score = frp * alignment * proximity
      return { fire: f, dist, score }
    })
    .filter((c) => c.score > 0)
    .sort((a, b) => b.score - a.score)
  return candidates.slice(0, maxPaths).map((c) => ({ from: { lat: c.fire.lat, lon: c.fire.lon }, to: center }))
}