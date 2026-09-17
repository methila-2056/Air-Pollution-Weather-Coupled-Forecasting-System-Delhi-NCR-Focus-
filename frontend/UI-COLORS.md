# AeroCast-NCR — UI Colour Reference

Single reference for every colour used in the frontend. All design tokens are defined in
`tailwind.config.js`; raw-hex chart/status colours live in `src/lib/theme.ts`. The AQI colour
scale lives in `src/lib/aqi.ts` and is the single source for badges, cards, maps and heatmaps.

## 1. Brand palette (Tailwind tokens — `tailwind.config.js`)

| Token | Hex | Usage |
|---|---|---|
| `navy-900/800/700/600` | `#0a0e27` … `#252b68` | Dark navy (reserved for header/landing) |
| `inst-50` | `#f0f5fa` | Light tint: icon chips, badges, active-nav mobile bg |
| `inst-100` | `#dbe8f3` | Tint + light borders (login demo panel) |
| `inst-200` | `#bcd5ea` | Selection/skeleton tints, dark-header secondary text |
| `inst-300` | `#8fb9dd` | Hover borders, dark-header chip borders |
| `inst-400/500` | `#5a93c9` / `#2f76b4` | Focus rings, secondary fills |
| `inst-600` | `#1d5f9c` | Active station border, links/footer icon |
| **`inst-700`** | **`#0B4F8A`** | **Primary brand** — buttons, active nav, chart lines |
| `inst-800` | `#0a4172` | Button hover, national header bg |
| `inst-900` | `#0a3458` | Deep-blue text (login header) |
| `accent-cyan` | `#0891b2` | Wind arrows, atmospheric logo icon |
| `accent-green/amber/red` | `#16a34a` / `#d97706` / `#dc2626` | Semantic status (see §3/§4) |

> **Rule:** non-data colours must use `inst-*` / `navy-*` tokens. Never `blue-*` / `sky-*`.

## 2. AQI / CPCB category scale — `src/lib/aqi.ts` (single source)

Used by `AQIBadge`, `AQICard`, `StationMap`, spatial heatmap and station tiles via `aqiStyle()`.
Chip/Tailwind classes are matched to the hex of each row.

| Category | Range | Hex | Tailwind chip / bar / text |
|---|---|---|---|
| Good | 0–50 | `#16a34a` | `bg-green-100 text-green-800` / `bg-green-600` / `text-green-700` |
| Satisfactory | 51–100 | `#ca8a04` | `bg-yellow-100 text-yellow-800` / `bg-yellow-600` / `text-yellow-700` |
| Moderate | 101–200 | `#d97706` | `bg-amber-100 text-amber-800` / `bg-amber-600` / `text-amber-700` |
| Poor | 201–300 | `#dc2626` | `bg-red-100 text-red-800` / `bg-red-600` / `text-red-700` |
| Very Poor | 301–400 | `#9333ea` | `bg-purple-100 text-purple-800` / `bg-purple-600` / `text-purple-700` |
| Severe | 401+ | `#7f1d1d` | `bg-red-200 text-red-900` / `bg-red-900` / `text-red-900` |
| No data | — | `#94a3b8` | `bg-slate-100 text-slate-500` / `bg-slate-300` / `text-slate-400` |

- `aqiStyle(aqi)` returns `{ label, hex, chip, text, bar }` — use for all AQI-tinted UI.
- `aqiCategoryHex(category)` resolves a hex by category label (spatial heatmaps).
- `readableOnHex(hex)` returns `#0f172a` (dark) or `#ffffff` by background luminance — use whenever text sits on a solid colour bar/badge.

## 3. Chart tokens — `src/lib/theme.ts`

| Token | Hex | Usage |
|---|---|---|
| `CHART.brand` | `#0B4F8A` | Forecast lines/areas, bar charts, fallback |
| `CHART.grid` | `#e2e8f0` | Cartesian grid |
| `CHART.axis` | `#64748b` | Axis strokes/labels |
| `CHART.tooltipBg / Border / Label` | `#ffffff` / `#e2e8f0` / `#334155` | Tooltip |
| `CHART.naaqsPm25` | `#d97706` | NAAQS 60 reference line |
| `POLLUTANT_COLORS` | `aqi #0B4F8A · pm25 #dc2626 · pm10 #d97706 · o3 #059669 · no2 #7c3aed` | Pollutant series |
| `STATUS.good / warn / bad / muted` | `#16a34a` / `#d97706` / `#dc2626` / `#cbd5e1` | SVG meters, band bars |

`pollutantColor(key)` strips a `_pred` suffix to resolve the pollutant token.

## 4. Semantic status ladder

One ladder everywhere: **minimal/OK = green-700 · watch/low = amber-700 · warning/medium = orange-700 · severe/high = red-700**.

| Component | Mapping |
|---|---|
| `AlertList.tsx` | SEVERE red-700 · WARNING orange-700 · WATCH amber-700 · INFO `inst-700` |
| `InversionPanel.tsx` | strength Strong/Moderate/Weak/None = red/orange/amber/green; risk HIGH/MEDIUM/LOW/MINIMAL = red/orange/amber/green |
| `TransportChain.tsx` | risk HIGH red-700 · MODERATE amber-700 · LOW green-700; step icon tints orange/amber/cyan (wind) |
| `StatusBar` (`SystemStatus.tsx`) | offline `bg-red-500` · stale `bg-amber-400` · live `bg-emerald-400` |

## 5. Surface borders & text-on-colour

- `.card` uses a **low-opacity but visible** border: `border-slate-300/60` (clearer than the old
  `border-slate-200` on the `slate-100` page background, still subtle).
- Text on solid colour backgrounds (AQI tiles, GRAP pills) must never be hardcoded `text-white` —
  use `readableOnHex(bgHex)` so light categories (Good/Satisfactory/Moderate, no-data, inactive GRAP)
  get dark navy text and dark categories get white text.
- GRAP badges (`GrapPanel`, `AlertsSection`) colour text from the backend hex via `readableOnHex()`;
  an inactive GRAP badge renders as a readable grey pill (`#e2e8f0` bg / `#334155` text) instead of
  invisible white-on-white.

## 6. Files centralised

| File | Change |
|---|---|
| `src/lib/aqi.ts` | Canonical AQI hex + matching chip/text/bar classes; `aqiCategoryHex()` |
| `src/lib/theme.ts` | New: chart/status/pollutant tokens |
| `src/pages/SpatialForecastPage.tsx` | Duplicate AQI palette removed → `aqiStyle()/aqiCategoryHex()` |
| `src/pages/LoginPage.tsx` | `blue-*` → `inst-*` throughout (header, inputs, buttons, demo panel) |
| `src/components/Layout.tsx` | avatar `bg-sky-700`→`inst-700`; `blue-200/100`, `blue-300/40` → `inst-*` |
| `src/components/SystemStatus.tsx` | `text-blue-100` → `inst-100` |
| `src/components/AlertList.tsx` | INFO `blue-*` → `inst-*` |
| `src/auth/ProtectedRoute.tsx` | spinner `blue-*` → `inst-*` |
| `src/components/TransportChain.tsx` | wind step `sky-*` → `cyan-*` (semantic wind) |
| `src/components/ForecastChart.tsx` | default `#0B4F8A` + chart tokens from `CHART` |
| `src/pages/Forecast72h.tsx` | `TAB_COLORS` → `pollutantColor()`; chart tokens |
| `src/pages/Overview.tsx` | chart `#3b82f6` (off-brand blue) → `CHART.brand` |
| `src/pages/Dashboard.tsx` | tooltip + preview chart hexes → `CHART` tokens |
| `src/components/ModelPerformance.tsx` | chart hexes → `CHART`; XGBoost brand token |
| `src/components/AtmosphericState.tsx` | gauge/band hexes → `STATUS` |
| `src/components/DispersionMeter.tsx` | meter hexes → `STATUS` |
| `src/pages/Atmosphere.tsx` | PBL bar hexes → `STATUS` |
| `src/index.css` | `.card` border `slate-200` → `slate-300/60` (low-opacity, visible) |
| `src/pages/Dashboard.tsx` | AQI hero tile text = `readableOnHex(rankStyle.hex)` |
| `src/components/GrapPanel.tsx` | badge text via `readableOnHex`; inactive badge = grey pill |
| `src/components/AlertsSection.tsx` | GRAP pill text via `readableOnHex` (no fixed white) |