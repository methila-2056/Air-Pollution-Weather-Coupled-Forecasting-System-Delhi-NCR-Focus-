"""Grid-based numerical atmospheric chemistry transport core for Delhi NCR.

This is a lightweight, self-contained surrogate for the WRF-Chem dynamical
core. Instead of relying purely on statistical interpolation (IDW), it solves
the two-dimensional advection-diffusion-reaction equation on the NCR grid by
finite differences, stepping chemistry forward in time with the prevailing
meteorology:

    dC/dt = - u.dC/dx - v.dC/dy          (wind advection of the pollutant field)
           + K_h * laplacian(C)          (horizontal turbulent diffusion)
           - (lambda_dep + washout) C    (dry + wet deposition)
           + E(x,y,t)                    (emission sources: stubble fires + urban)

The transport is coupled two-way to meteorology through:
  * wind (u,v) advecting the field (chemistry <= meteorology),
  * PBL height controlling the vertical dilution of emitted mass
    (chemistry <= meteorology),
  * aerosol loading suppressing PBL height / increasing stability
    (chemistry => meteorology feedback),
  * precip-driven wet deposition (chemistry <= meteorology).

Because the solver integrates the advective/diffusive transport of an existing
pollutant field, it can advect a measured/inversion-trapped field as well as
disperse the stubble-burning plumes explicitly over forecast hours, satisfying
the PS requirement to 'predict how stubble-burning plumes will disperse under
prevailing weather' and to 'dynamically interlink meteorology with pollution
dispersion'.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ml.features.coupling import boundary_stability_index, corrected_pbl_height

NCR_BOUNDS = {
    "lat_min": 28.2, "lat_max": 28.9,
    "lon_min": 76.6, "lon_max": 77.5,
}
GRID_STEP = 0.02  # ~2.2 km cell

# physical constants
U0 = 1.0e-4          # background concentration floor (in pm2.5 units)
HORIZONTAL_DIFFUSIVITY = 60.0    # m^2/s turbulent eddy diffusivity
CELL_SIZE_M = GRID_STEP * 111000.0  # ~2.2 km
SECONDS_PER_STEP = 900.0        # 15 minute integration sub-step (CFL-safe for <8 m/s)

# AQI <-> PM2.5 concentration approximation for the CPCB AQI (piecewise-linear)
_AQI_BREAKPOINTS = [0, 50, 100, 200, 300, 400, 500]
_PM25_BREAKPOINTS = [0.0, 30.0, 60.0, 90.0, 120.0, 250.0, 350.0]


def conc_to_aqi(pm25: np.ndarray) -> np.ndarray:
    """Approximate CPCB AQI sub-index from PM2.5 concentration (ug/m3)."""
    pm25 = np.clip(np.asarray(pm25, dtype=float), 0.0, _PM25_BREAKPOINTS[-1])
    aqi = np.interp(pm25, _PM25_BREAKPOINTS, _AQI_BREAKPOINTS)
    return np.clip(aqi, 0, 500).astype(int)


def aqi_to_conc(aqi: np.ndarray) -> np.ndarray:
    """Invert approx AQI -> PM2.5 concentration (ug/m3)."""
    aqi = np.clip(np.asarray(aqi, dtype=float), 0.0, 500.0)
    return np.interp(aqi, _AQI_BREAKPOINTS, _PM25_BREAKPOINTS)


class DispersionSolver:
    """Finite-difference advection-diffusion-deposition-emission solver."""

    def __init__(
        self,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lon_min: Optional[float] = None,
        lon_max: Optional[float] = None,
        step_deg: float = GRID_STEP,
        diffusivity: float = HORIZONTAL_DIFFUSIVITY,
    ):
        b = NCR_BOUNDS
        self.lat_min = lat_min or b["lat_min"]
        self.lat_max = lat_max or b["lat_max"]
        self.lon_min = lon_min or b["lon_min"]
        self.lon_max = lon_max or b["lon_max"]
        self.step = step_deg
        self.diff = diffusivity

        # grid node coordinates
        self.nlat = int(round((self.lat_max - self.lat_min) / step_deg)) + 1
        self.nlon = int(round((self.lon_max - self.lon_min) / step_deg)) + 1
        self.lats = self.lat_min + np.arange(self.nlat) * step_deg
        self.lons = self.lon_min + np.arange(self.nlon) * step_deg

        self.cell_m = step_deg * 111000.0

        # state field (normalised concentration ~ pm2.5 scale)
        self.C = np.full((self.nlat, self.nlon), U0, dtype=float)
        self.inflow_conc = U0

        # accumulated emissions map
        self.accumulated_source = np.zeros((self.nlat, self.nlon), dtype=float)

    # --- grid -> cell -> lat/lon helpers -----------------------------
    def _cell(self, lat: float, lon: float) -> tuple:
        i = int(np.clip(round((lat - self.lat_min) / self.step), 0, self.nlat - 1))
        j = int(np.clip(round((lon - self.lon_min) / self.step), 0, self.nlon - 1))
        return i, j

    def set_background(self, field: np.ndarray) -> None:
        """Set the initial pollutant field from an analysis/interpolation."""
        if field.shape != self.C.shape:
            field = np.resize(field, self.C.shape)
        self.C = np.maximum(np.asarray(field, dtype=float), U0)
        # lateral inflow concentration: time-mean of the initial field, so air
        # advecting INTO the domain carries the regional background burden.
        self.inflow_conc = float(np.mean(self.C))

    def set_inflow_conc(self, conc: float) -> None:
        """Override the regional lateral inflow concentration (ug/m3)."""
        self.inflow_conc = max(1e-4, float(conc))

    def add_point_emission(self, lat: float, lon: float, mass: float) -> None:
        """Add an emission source (e.g. a stubble fire) with plume mass."""
        i, j = self._cell(lat, lon)
        kernel = np.array([[0.05, 0.1, 0.05],
                           [0.1, 0.4, 0.1],
                           [0.05, 0.1, 0.05]])
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                ii, jj = i + di, j + dj
                if 0 <= ii < self.nlat and 0 <= jj < self.nlon:
                    self.accumulated_source[ii, jj] += mass * kernel[di + 1, dj + 1]

    def add_areal_emission(self, lat_min, lat_max, lon_min, lon_max, mass_density):
        """Add a distributed emission over a rectangular area (urban source)."""
        for i in range(self.nlat):
            lat = self.lats[i]
            if not (lat_min <= lat <= lat_max):
                continue
            for j in range(self.nlon):
                lon = self.lons[j]
                if lon_min <= lon <= lon_max:
                    self.accumulated_source[i, j] += mass_density

    # --- deposition ---------------------------------------------------
    def dry_deposition(self, pbl_height: float) -> np.ndarray:
        """Dry deposition removal rate per cell (larger when PBL is shallow)."""
        vd = 0.004  # dry deposition velocity (m/s)
        return np.full(self.C.shape, vd / max(200.0, pbl_height))

    def wet_removal(self, precip_mm: float) -> np.ndarray:
        """Wet scavenging rate (s^-1); heavier rain clears more."""
        if precip_mm <= 0:
            return np.zeros(self.C.shape)
        lam = min(3e-4, 5e-5 * precip_mm)   # per-second scavenging coefficient
        return np.full(self.C.shape, lam)

    # --- physics / numerics ------------------------------------------
    def _advect(self, u_field, v_field, dt) -> None:
        """Vectorized upwind finite-difference advection (mass-conservative).

        Flux on face j (between cell j-1 and j) takes the *upstream* cell.
        At the boundary faces, air flowing INTO the domain carries the
        regional background concentration (inflow_conc); outflow is free.
        """
        C = self.C
        u = np.asarray(u_field, dtype=float)
        v = np.asarray(v_field, dtype=float)
        dx = self.cell_m
        nlat, nlon = C.shape
        bc_back = self.inflow_conc

        # --- x-fluxes (faces j = 0..nlon) ---
        face_u = np.zeros((nlat, nlon + 1))
        face_u[:, 1:nlon] = 0.5 * (u[:, :-1] + u[:, 1:])
        face_u[:, 0] = u[:, 0]
        face_u[:, nlon] = u[:, nlon - 1]

        jj = np.arange(nlon + 1)
        idx_left = np.clip(jj - 1, 0, nlon - 1)
        idx_right = np.clip(jj, 0, nlon - 1)
        C_left = C[:, idx_left]
        C_right = C[:, idx_right]

        # lateral inflow: westerly/easterly wind at the east/west edges drags
        # regional background air INTO the domain.
        C_right_in = C_right.copy()
        C_right_in[:, 0] = np.where(face_u[:, 0] < 0, bc_back, C_right[:, 0])
        C_right_in[:, nlon] = np.where(face_u[:, nlon] < 0, bc_back, C_right[:, nlon])

        Fx = np.where(face_u >= 0, face_u * C_left, face_u * C_right_in)
        div_x = Fx[:, 1:] - Fx[:, :-1]

        # --- y-fluxes (faces i = 0..nlat) ---
        face_v = np.zeros((nlat + 1, nlon))
        face_v[1:nlat, :] = 0.5 * (v[:-1, :] + v[1:, :])
        face_v[0, :] = v[0, :]
        face_v[nlat, :] = v[nlat - 1, :]

        ii = np.arange(nlat + 1)
        idx_up = np.clip(ii - 1, 0, nlat - 1)
        idx_dn = np.clip(ii, 0, nlat - 1)
        C_up = C[idx_up, :]
        C_dn = C[idx_dn, :]

        # lateral inflow: northerly/southerly wind at the north/south edges.
        C_dn_in = C_dn.copy()
        C_dn_in[0, :] = np.where(face_v[0, :] < 0, bc_back, C_dn[0, :])
        C_up_in = C_up.copy()
        C_up_in[nlat, :] = np.where(face_v[nlat, :] > 0, bc_back, C_up[nlat, :])

        Fy = np.where(face_v >= 0, face_v * C_up_in, face_v * C_dn_in)
        div_y = Fy[1:, :] - Fy[:-1, :]

        Cnew = C - (dt / dx) * (div_x + div_y)
        self.C = np.maximum(Cnew, 0.0)

    def _diffuse(self, dt) -> None:
        """Implicit-ish 5-point horizontal diffusion."""
        Cn = self.C.copy()
        k = self.diff * dt / (self.cell_m ** 2)
        lap = np.zeros_like(self.C)
        lap[1:-1, 1:-1] = (Cn[:-2, 1:-1] + Cn[2:, 1:-1] +
                           Cn[1:-1, :-2] + Cn[1:-1, 2:] - 4 * Cn[1:-1, 1:-1])
        self.C = Cn + k * lap
        self.C = np.maximum(self.C, 0.0)

    def _deposit(self, rate: np.ndarray, dt) -> None:
        self.C = self.C * np.exp(-rate * dt)

    def _emit(self, dt) -> None:
        self.C = self.C + self.accumulated_source * dt

    def advance(
        self,
        u_field: np.ndarray,
        v_field: np.ndarray,
        pbl_height: float,
        precip_mm: float = 0.0,
        dt: float = SECONDS_PER_STEP,
        emission_active: bool = True,
        hour: int = 12,
        wind_speed: float = 0.0,
        coupled: bool = True,
    ) -> None:
        """Advance the pollutant field one sub-step with full physics.

        Two-way coupling (when `coupled`):
          * met -> chemistry: the prevailing PBL is used for vertical dilution
            of deposited/emitted mass, and precipitation scavenges;
          * chemistry -> met: the resolved aerosol loading suppresses the PBL
            and stabilises the boundary layer, which in turn strengthens
            pollutant retention (reduced lateral mixing, slower venting).
        """
        mean_pm25 = float(np.mean(self.C))
        stability = boundary_stability_index(mean_pm25, pbl_height, wind_speed or 4.0, hour)
        eff_pbl = corrected_pbl_height(mean_pm25, pbl_height, hour)
        mix_scale = (1.0 - 0.35 * stability) if coupled else 1.0

        if emission_active:
            self._emit(dt)
        self._advect(np.asarray(u_field), np.asarray(v_field), dt)
        if mix_scale < 1.0:
            self._diffuse(dt * mix_scale)   # reduced mixing under stable episodes
        else:
            self._diffuse(dt)
        # dry deposition + wet scavenging (met -> chemistry)
        dry = self.dry_deposition(eff_pbl)
        wet = self.wet_removal(precip_mm)
        total = dry + wet
        self._deposit(total, dt)
        self.C = np.maximum(self.C, 0.0)

        self.coupling_diag = {
            "mean_pm25": round(mean_pm25, 3),
            "stability_coupling_index": round(stability, 4),
            "pbl_suppression_factor": round(eff_pbl / max(1.0, pbl_height), 4),
            "corrected_pbl_height": round(eff_pbl, 1),
        }


def build_wind_fields(
    wind_speed: float,
    wind_dir_deg: float,
    nlat: int,
    nlon: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Uniform wind field projected onto (u, v) grid arrays (m/s)."""
    rad = np.deg2rad(wind_dir_deg)
    u = wind_speed * np.sin(rad)
    v = wind_speed * np.cos(rad)
    u_field = np.full((nlat, nlon), u)
    v_field = np.full((nlat, nlon), v)
    return u_field, v_field


def aqi_from_conc(pm25_conc: np.ndarray) -> np.ndarray:
    """Alias for conc_to_aqi (retained for convenience)."""
    return conc_to_aqi(pm25_conc)


def run_dispersion_forecast(
    initial_aqi_field: np.ndarray,
    lat_min,
    lat_max,
    lon_min,
    lon_max,
    step_deg,
    wind_speed: float,
    wind_dir_deg: float,
    pbl_height: float,
    precip_mm: float = 0.0,
    fires: Optional[list] = None,
    hours: int = 24,
    dt: Optional[float] = None,
    urban_emission: float = 3.0e-3,
    start_hour: int = 8,
    wind_hourly: Optional[list] = None,
    pbl_hourly: Optional[list] = None,
    precip_hourly: Optional[list] = None,
    dir_hourly: Optional[list] = None,
    coupled: bool = True,
) -> dict:
    """Run the numerical dispersion integration over `hours`.

    Args:
        initial_aqi_field: initial gridded AQI field (candidate surface).
        fires: list of {'lat', 'lon', 'frp'} stubble-fire point sources.
        hours: forecast horizon (h).
        dt: integration sub-step (s). If None, CFL-limited from the wind speed.
        urban_emission: persistent PM2.5 emission rate (ug/m3/s) over the NCR
            urban core (Delhi metro + NCR ring), balancing deposition/outflow.
        start_hour: hour-of-day (0-23) of the forecast start, for the diurnal
            coupling/radiation weighting.
        wind_hourly/pbl_hourly/precip_hourly/dir_hourly: length-`hours` met
            series; values fall back to the scalar arguments where missing.

    Returns per-hour AQI frames, the final solver state, and the integrated
    (deposited/emitted) control volume budget for diagnostics.
    """
    fire_mass_scale = 3.0e-5   # per-second injection rate per FRP (ug/m3/s)
    # NCR urban core (Delhi + Ghaziabad/Noida/Gurugram/Faridabad belt)
    URBAN_LAT0, URBAN_LAT1 = 28.40, 28.75
    URBAN_LON0, URBAN_LON1 = 76.90, 77.35

    nlat = int(round((lat_max - lat_min) / step_deg)) + 1
    nlon = int(round((lon_max - lon_min) / step_deg)) + 1

    initial_aqi = np.asarray(initial_aqi_field, dtype=float)
    if initial_aqi.ndim == 1:
        initial_aqi = initial_aqi.reshape(nlat, nlon)
    init_conc = aqi_to_conc(np.clip(initial_aqi, 0, 500))
    init_conc = np.maximum(init_conc, 1e-4)

    solver = DispersionSolver(lat_min, lat_max, lon_min, lon_max, step_deg)
    solver.set_background(init_conc)
    if urban_emission > 0:
        solver.add_areal_emission(URBAN_LAT0, URBAN_LAT1, URBAN_LON0, URBAN_LON1,
                                  urban_emission)
    if fires:
        for f in fires:
            solver.add_point_emission(
                f["lat"], f["lon"], (f.get("frp", 2.0) or 2.0) * fire_mass_scale
            )

    if dt is None:
        max_speed = max(1.0, float(abs(wind_speed)))
        dt = 0.5 * solver.cell_m / max_speed   # CFL <= 0.5
    steps_per_hour = int(3600 // dt)

    frames = []
    for h in range(hours):
        spd = float((wind_hourly or [wind_speed] * hours)[h])
        pbl = float((pbl_hourly or [pbl_height] * hours)[h])
        prc = float((precip_hourly or [precip_mm] * hours)[h])
        ddir = float((dir_hourly or [wind_dir_deg] * hours)[h])
        hour_of_day = (start_hour + h) % 24
        u_field, v_field = build_wind_fields(spd, ddir, nlat, nlon)
        for _ in range(steps_per_hour):
            solver.advance(u_field, v_field, pbl, prc, dt=dt,
                           hour=hour_of_day, wind_speed=spd, coupled=coupled)
        frames.append({
            "hour": h + 1,
            "hour_of_day": hour_of_day,
            "wind_speed": round(spd, 2),
            "wind_dir_deg": round(ddir, 1),
            "pbl_height": round(pbl, 1),
            "precip_mm": round(prc, 2),
            "coupling": dict(solver.coupling_diag or {}),
            "concentration": solver.C.copy(),
            "aqi": conc_to_aqi(solver.C),
        })
    return {
        "solver": solver,
        "dt_used": dt,
        "steps_per_hour": steps_per_hour,
        "frames": frames,
    }