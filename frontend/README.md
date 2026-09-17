# AeroCast-NCR Frontend

React + TypeScript (Vite + Tailwind) dashboard for AeroCast-NCR.

## Pages

- `/` and `/dashboard` — Atmospheric Intelligence control room: NCR KPIs,
  station AQI grid, 72h risk band, PM2.5 preview, atmospheric state, GRAP,
  alerts and the NCR monitoring map
- `/overview` — operational overview: current AQI, 72h forecast curves
  (Recharts), inversion, plume risk, explainability and coupling panels
- `/forecast` — per-station 72h pollutant forecasts + risk band + CSV export
- `/map` — Delhi NCR monitoring map (Leaflet): station AQI markers, FIRMS
  hotspots, plume-transport KPI cards and station snapshot grid
- `/atmosphere` — weather, PBL/ventilation, inversion, coupling and dispersion
  diagnostics
- `/fire-plume` (alias `/stubble`) — stubble-burning plume risk and hotspot map
- `/explanation` — SHAP driver bars + natural-language forecast explanation
- `/alerts` — GRAP current stage + alert list (INFO → SEVERE)
- `/performance` — cross-model performance (persistence / RF / XGBoost / GRU)
- `/spatial` — NCR map: statistical IDW grid **or** live numerical dispersion
  field with fire-plume overlay and coupling diagnostics
- `/data` — CSV export/import tools
- `/profile` — session / account card
- `/login` — demo auto-filled sign-in

## Commands

```bash
npm ci            # install
npm run dev       # dev server :5173, proxies /api → :8000
npm run build     # tsc type-check + vite production build
npm run preview   # serve the production build
```

## Structure

```
src/
  api/client.ts       axios wrapper — all backend calls
  auth/               AuthContext + ProtectedRoute
  types/index.ts      shared TypeScript interfaces
  lib/                aqi helpers, forecast run-dedupe
  components/         UI building blocks (AQIBadge, StatCard, StationMap, …)
  pages/              route-level pages
  App.tsx             route table + shell
  Layout.tsx          navigation shell
```

## Conventions

- One feature per page slice; keep API access in `src/api/client.ts`.
- AQI colouring is centralised in `src/lib/aqi.ts` (CPCB breakpoints) and used
  by every badge, bar and legend.
- Light dashboard theme; Tailwind utilities only.