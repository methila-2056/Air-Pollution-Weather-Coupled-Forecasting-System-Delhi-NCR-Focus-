# AeroCast-NCR Frontend

React + TypeScript (Vite + Tailwind) dashboard for AeroCast-NCR.

## Pages

- `/` — overview: current AQI, forecast curves (Recharts), weather, plume risk
- `/forecast` — per-station 72h pollutant forecasts + explainability
- `/spatial` — NCR map: statistical IDW grid **or** live numerical dispersion
  field with fire-plume overlay and coupling diagnostics
- `/alerts`, `/settings`

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
  types/index.ts      shared TypeScript interfaces
  components/         UI building blocks (AQIBadge, StatCard, …)
  pages/              route-level pages
  App.tsx             route table + shell
  Sidebar.tsx         navigation
```

## Conventions

- One feature per page slice; keep API access in `src/api/client.ts`.
- AQI colouring is centralised on the AQI category → colour map used by every
  heatmap/legend (`AQI_COLORS` in the spatial page).
- Dark dashboard theme; Tailwind utilities only.