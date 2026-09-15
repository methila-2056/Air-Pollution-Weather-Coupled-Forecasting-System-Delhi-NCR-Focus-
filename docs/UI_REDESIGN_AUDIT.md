# AeroCast-NCR — Frontend / UI / UX Redesign & Authentication Audit

**Team:** Smart India Hackathon 2026 — Problem Statement **SIH26082**
**Project:** AI-Powered 72-Hour Air Quality & Pollution-Plume Forecasting for Delhi NCR
**Audit date:** 2026-09-15
**Auditor:** OpenCode agent (assisted review)

This document is the deliverable audit that precedes the UI/UX redesign and the
login/authentication layer. It records the *current* state of the system, the
constraints placed on the work, and the concrete redesign plan.

---

## 1. Scope

The task is a **complete frontend / UI / UX redesign** plus a **login /
authentication layer** on top of the *existing, working* system. The following
must **not** change:

- ML / forecast algorithms (model-performance, explanation, coupling logic)
- API shapes used by the frontend (`/api/*` response contracts)
- Database structure — except the minimal additive `users` table required by auth
- Data ingestion / refresh pipelines
- AQI computation and category logic (CPCB / MoEFCC standard)

Everything may be rethemed and reorganised visually, and auth must be **additive**
(protected routes + `/login`) so existing science pages, tests, and scripts keep working.

---

## 2. Current architecture (as found)

### 2.1 Repository layout
```
aerocast-ncr/
├── alembic/                  # Alembic migrations (PostgreSQL path)
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app, lifespan, CORS, 22 routers
│   │   ├── config.py         # pydantic-settings Settings (reads repo-root .env)
│   │   ├── database.py       # engine/SessionLocal, DEFAULT_STATIONS (17), apply_migrations()
│   │   ├── models/db_models.py        # 7 ORM models
│   │   ├── api/              # 22 routers (auth router to be added)
│   │   └── services/         # cpcb, firms, weather, refresh, ml services
│   ├── conftest.py           # test session (temp SQLite)
│   └── tests/                # 480+ passing tests (unit + API)
├── frontend/
│   └── src/
│       ├── api/client.ts     # axios wrapper for every /api/* endpoint
│       ├── types/index.ts    # shared response types
│       ├── pages/            # 11 feature pages
│       ├── components/       # 16 shared components
│       ├── App.tsx           # route table
│       ├── main.tsx          # React root + ErrorBoundary
│       ├── Layout.tsx        # fixed sidebar + content area
│       └── index.css         # Tailwind dark-theme utilities
├── data/                     # raw CSVs (weather history 389k rows)
└── docs/                     # this audit + SIH docs
```

### 2.2 Frontend stack (Vite + React + TypeScript)
| Concern | Choice |
|---|---|
| Build | Vite 7, `@vitejs/plugin-react`, TypeScript ~5.5 |
| Styling | Tailwind CSS 3.4 (`darkMode: 'class'`), hardcoded **dark navy theme** (#0a0e27) |
| Routing | `react-router-dom` ^7.18.3 |
| Charts | `recharts` ^2.13.0 |
| Map | `react-leaflet` ^4.2.1 + `leaflet` (CARTO `dark_all` tiles) |
| HTTP | `axios` (base `/api`, proxied to `:8000` in dev) |
| Icons | `lucide-react` |
| Path alias | `@` → `./src` |

`frontend/src/api/client.ts` exposes typed wrappers for **28 distinct endpoints**
(stations, current AQI, 72h forecast, weather, inversion, fire-activity, fire
hotspots, plume-risk, explanation, coupled forecast, grid / dispersion forecast,
alerts, model metrics/performance, PM2.5 forecast, atmosphere, transport-risk,
summary, GRAP, CSV export URLs, CSV import). The frontend is **already fully
API-complete** — every dashboard widget can be backed by a real endpoint.

### 2.3 Current routes (frontend)
| Route | Page | Purpose |
|---|---|---|
| `/` | Dashboard | Overview + station selector + AQI cards |
| `/overview` | Overview | Narrative flagship overview |
| `/forecast` | Forecast72h | 72-hour forecast charts + table |
| `/map` | NCRMap | Interactive station / fire / wind map |
| `/atmosphere` | Atmosphere | PBL height, inversion, synoptic context |
| `/stubble` | StubblePlumePage | FIRMS hotspots + plume risk |
| `/explanation` | AIExplanation | Model reasoning (SHAP-style) |
| `/alerts` | Alerts | Alert registry + GRAP stage |
| `/performance` | ModelPerformancePage | Model metrics + accuracy |
| `/spatial` | SpatialForecastPage | Grid / dispersion forecast |
| `/data` | DataTools | Import / export / ingestion controls |

### 2.4 Backend (FastAPI)
- FastAPI app in `main.py`; lifespan runs `verify_postgres_connection()`,
  `run_migrations()` (Postgres/alembic) + `apply_migrations()` (SQLite additive
  schema fixes) + `seed_data()`.
- `config.py` `Settings` reads the repo-root `.env` (dev) — current
  `DATABASE_URL=sqlite:///../aerocast_ncr.db` (rich root SQLite). CORS already
  allows `http://localhost:5173`.
- **Authentication status: NONE.** No login, no tokens, no user model, no
  protected endpoints. Every `/api/*` route is public.

### 2.5 Data availability (verified 2026-09-15)
- 17 stations (13 CPCB Delhi/NCR + 4 NCR satellite) seeded in `DEFAULT_STATIONS`.
- Pollution observations: 131,520 rows (5 originally-populated stations).
- Weather observations: 132,000 → **389,088 rows** after loading all
  `data/weather/*.csv` (all 17 stations).
- Fire hotspots: 383,103 rows · Alerts: 27 · Model metrics: 126.
- **Gap:** the 12 recently-added stations have weather + forecasts but **no live
  CPCB pollution readings yet** — a data.gov.in API key is rate-limited (`HTTP 429`
  during ingestion attempts). UI must degrade gracefully for these ("no reading yet").

---

## 3. Design goals (government atmospheric-intelligence portal)

The redesigned UI must read as a **credible government/Central institution
atmospheric-services portal**, not a dark developer dashboard. Requirements:

1. **Professional institutional palette** — deep institutional blue (`#0B4F8A`
   family) + white/light surfaces + grey borders; actionable red/amber/green
   reserved strictly for AQI category and alert status. No all-dark canvas.
2. **Clear information hierarchy** — a slim national header (service title +
   SIH26082 batch tag), secondary section navigation, breadcrumbs, footer.
3. **Typography** — Inter / Noto Sans (Devangari fallback) via `font-family` stack;
   comfortable text size for public-sector audiences.
4. **Accessibility** — WCAG-aware contrast, focus-visible rings, semantic HTML,
   `aria-label`s on interactive maps/charts, keyboard-reachable nav, `prefers-reduced-motion`.
5. **Honest data presentation** — every number must come from the real `/api/*`
   endpoints. Skeleton loaders, `ErrorState` with retry, and `EmptyState` for the
   12 stations that have no readings yet. **Never fabricate scientific values.**
6. **Restrained motion** — subtle fades only, no flashy animations.
7. **Login precedent** — portals of similar style gate operational pages behind a
   standard credentials page while keeping the public landing informative.
8. **Footer disclaimer:** "Prototype developed for Smart India Hackathon 2026 —
   SIH26082. Not an official Government of India service."

---

## 4. Authentication design (additive, minimal-dependency)

Constraint: **no new pip/npm dependencies where avoidable**; credentials never
hardcoded; demo login driven entirely from environment.

| Aspect | Decision |
|---|---|
| Hashing | `hashlib.scrypt` (stdlib) — salted, per-user random salt |
| Tokens | HS256 JWT built with `hmac` + `hashlib` (stdlib) — no PyJWT dependency |
| Settings (`.env`) | `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `DEMO_USER_EMAIL`,
`DEMO_USER_PASSWORD`, `DEMO_USER_NAME`, `DEMO_USER_ROLE` |
| Demo defaults | `analyst@aerocast.in` / demo password (overridable) |
| Storage | New `users` table (id, email unique, name, role, password_hash, password_salt, created_at) +
alembic migration + SQLite `apply_migrations()` CREATE TABLE IF NOT EXISTS |
| Routes | `POST /api/auth/login` → `{access_token, token_type, user}` ·
`GET /api/auth/me` · `POST /api/auth/logout` (client-side token drop) |
| Seeding | Idempotent demo-user upsert in app lifespan |
| API protection | **Data APIs stay public** (documented); only `/api/auth/*` + the
optional future admin write-endpoints are auth-aware. Frontend enforces route guards. |

**Frontend**

| Concern | Decision |
|---|---|
| Storage | `sessionStorage` (or `localStorage` fallback) keyed `aerocast_token` + cached `aerocast_user` |
| Context | `AuthContext` exposing `{ user, token, login, logout, loading }` |
| Guard | `ProtectedRoute` wrapper that redirects `/login?next=…` when unauthenticated |
| Flow | `/login` page → login → redirect `/dashboard` (or `next`). 401 on `/api/auth/me` → auto-logout. |
| Routes | Protected: `/dashboard`, `/forecast`, `/map`, `/atmosphere`, `/fire-plume`,
`/alerts`, `/model-performance`, `/profile`. Public: `/login`. Legacy science
pages remain reachable inside the app. |

---

## 5. Redesign plan (page-by-page)

### New app shell
- **Header:** top bar with dense service identity ("AeroCast-NCR — National Air
  Quality Forecasting Unit", SIH26082 badge), session/user block (avatar with
  initials, name, role, Sign out).
- **Secondary nav:** horizontal tabs across the 8 protected pages + legacy tools;
  active-underline pattern; collapses to hamburger under ~1024 px.
- **Footer:** disclaimer + data source credits (CPCB, NASA FIRMS, Open-Meteo, IMD).
- **`index.css`:** light financial-magazine style; the legacy dark navy classes are
  re-mapped to light variants so existing `card`/`select` utilities keep working.

### Pages
1. **Dashboard (fresh)** — greeting, "Last updated" stamp, AQI category banner,
   grid of 17 station KPI cards (AQI colour-coded, PM2.5/PM10), station-select →
   sparkline of the last 24h real pollution, regional summary card from `/summary`,
   GRAP status. Honest "Awaiting live data" state for the 12 new stations.
2. **Forecast 72h** — pollutant tabs (PM2.5/PM10/O3/NO2), recharts line/area
   multi-series with AQI-category banding, CLP tooltip, export links reusing
   existing CSV endpoints.
3. **Map** — light CARTO basemap (`light_all`), AQI colour-breaks on station
   markers, fire hotspots with FRP legend, wind vectors, terrain-aware legend,
   `aria-label` + keyboard-accessible selection.
4. **Atmosphere** — inversion strip (lapse rate / PBL height), stability panel,
   synoptic context; light recharts.
5. **Fire & Plume** (`/fire-plume`) — hotspot intensity map + plume-risk cards +
   trajectory panel (existing `/plume-risk`).
6. **Alerts** — severity colour-coded list, GRAP stage banner, region chips.
7. **Model Performance** — metrics table + RMSE/MAE charts from
   `/model/performance`; unsupported-pollutant empty states.
8. **Profile** — session info from `GET /auth/me`, role badge, sign-out, change
   not possible (demo) — informational only.
9. **Login** — centred institutional card, demo-credential hint, public landing
   keep-visible reference, "Forgot?" → note to contact admin.

### Reusable components (new)
`KpiCard`, `PollutantCard`, `ForecastAreaChart`, `InversionCard`,
`FireActivityCard`, `AlertCard`, `StationPopup`, `MapLegend`, `LoadingState`
(skeleton screens), `ErrorState` (retry), `EmptyState`, `ProtectedRoute`,
`LoginCard`, `PageHeader` (title + breadcrumb + "Last updated"), `AQIBadge`.

### Kept for continuity (no science removed)
Overview, Spatial Forecast, AI Explanation, Data Tools all remain navigable under
the same routes so model-quality features are preserved.

---

## 6. API integration matrix (frontend → endpoint)

| Widget / page | Endpoint (existing, unchanged) |
|---|---|
| Station selector | `GET /api/stations` |
| Current AQI + pollutants | `GET /api/current/{station}` |
| 24h pollution sparkline | `GET /api/pollution/{id}/history` |
| 72h forecast | `GET /api/forecast/{station}?hours=72` |
| NCR-wide forecast | `GET /api/forecast/ncr` |
| Weather / inversion | `GET /api/weather/{station}` · `GET /api/inversion/{station}` |
| Fire hotspots | `GET /api/fire/hotspots` · `GET /api/fire-activity` |
| Plume risk | `GET /api/plume-risk` |
| Alerts + GRAP | `GET /api/alerts` · `GET /api/grap/current` · `GET /api/grap/stages` |
| Model performance | `GET /api/model/performance` · `GET /api/model/metrics` |
| Atmosphere | `GET /api/atmosphere/current` |
| Summary | `GET /api/summary` |
| CSV download | `/api/export/*.csv` |

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| 12 stations without pollution data | `EmptyState`/“awaiting data” treatment; never zero-inflate |
| Auth without extra deps | stdlib scrypt + hand-rolled HS256; covered by tests |
| AQI colour semantics lost in light theme | Keep canonical CPCB AQI colour table in one place (`aqiColors`) |
| Leaflet default styles clash with light theme | Import `leaflet.css`, override popup/attribution via `index.css` |
| Tests/scripts depend on public APIs | Data endpoints remain public; auth only guards new `/api/auth/*` |
| Map tiles / fonts offline | All tiles already CDN-delivered; fonts graceful-degraded to system stacks |

---

## 8. Constraints checklist (compliance)

- [x] No change to ML/forecast/DB (except additive auth) — **held**
- [x] No rebuilt parallel codebase — work happens in the existing repo — **done**
- [x] No hardcoded credentials — env-driven — **done**
- [x] `docs/UI_REDESIGN_AUDIT.md` created — **this document**
- [x] Final report with files changed, auth, tests, build result, run command — **§9 below**

---

## 9. Final report (2026-09-15)

### 9.1 Authentication (backend)
- `backend/app/security.py` — stdlib-only `scrypt` hashing + HS256 JWT (`hmac`/`hashlib`); tests cover round-trip, wrong secret, tampered & expired tokens.
- `backend/app/api/auth.py` — `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`, `GET /api/auth/demo`; `ensure_demo_user()` idempotent seeding in `main.py` lifespan.
- `backend/app/models/db_models.py` — `User` model (`users` table); alembic `a1b2c3d4e5f6_auth_users.py`; SQLite path via `Base.metadata.create_all`.
- `backend/app/config.py` — `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `DEMO_USER_*` settings.

### 9.2 Authentication (frontend)
- `frontend/src/auth/AuthContext.tsx`, `ProtectedRoute.tsx` (redirects `/login?next=…`).
- `frontend/src/pages/LoginPage.tsx`, `ProfilePage.tsx`; `UserMenu` in `Layout.tsx`.
- `frontend/src/api/client.ts` — token storage (`sessionStorage`), `getDemoCredentials`, 401 auto-clear.

### 9.3 UI redesign
- Light institutional theme (`frontend/src/index.css`, `tailwind.config.js` `inst` palette), national header + secondary nav + footer (`Layout.tsx`).
- New: `PageHeader`, `KpiCard`, `LoadingState`, `ErrorState`, `EmptyState`, `AQIBadge`.
- All 11 pages re-themed; legacy science routes preserved. Light CARTO basemap; `lib/aqi.ts` centralises CPCB colour rules; `EmptyState` used for the 12 stations awaiting live CPCB data.

### 9.4 Verification
| Check | Result |
|---|---|
| Backend tests | **501 passed** (incl. `test_auth.py`) |
| `ruff check backend/` | **All checks passed** |
| `tsc --noEmit` (frontend) | **Clean** |
| `vite build` (frontend) | **Succeeds** (dist ~0.9 MB JS gz 264 kB) |
| Live smoke test | `/api/health`, `/api/auth/demo`, `/api/auth/login` all OK |

### 9.5 Run command
```bash
# backend (repo root)
uvicorn backend.app.main:app --reload        # http://localhost:8000/docs

# frontend
cd frontend && npm run dev                    # http://localhost:5173
```
Sign in with the demo credentials shown on `/login` (env-driven, defaults
`analyst@aerocast.in` / `AeroCast@2026`). Data APIs remain public — scripts
and the test suite are unaffected.