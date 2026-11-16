<h1 align="center">FoodWasteOS</h1>

<p align="center">
  <strong>Predict tomorrow's demand per dish. Know how much to prepare. See what it saves.</strong>
</p>

<p align="center">
  A full-stack preparation-intelligence platform for restaurants, built end to end with React,
  FastAPI and PostgreSQL. It turns a kitchen's own sales and waste history into a daily prep plan,
  explains how confident each number is, and writes down every decision that was not obvious.
</p>

<p align="center">
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white">
  <img alt="React 18" src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black">
  <img alt="TypeScript 5" src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white">
  <img alt="PostgreSQL 16" src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white">
  <img alt="scikit-learn" src="https://img.shields.io/badge/scikit--learn-1.5+-F7931E?logo=scikitlearn&logoColor=white">
  <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
</p>

<p align="center">
  <a href="#architecture">Architecture</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="#how-the-forecast-works">How it works</a> ·
  <a href="#testing">Testing</a> ·
  <a href="#api">API</a> ·
  <a href="#deployment">Deployment</a>
</p>

> [!IMPORTANT]
> The core question is not *"how do we cook less?"* but *"how do we prepare the right amount?"* —
> enough to avoid selling out, not so much that food is thrown away. Every forecast is honest about
> its uncertainty: dishes without enough history are shown as `collecting_data` instead of a
> fabricated number.

## Overview

Food waste in restaurants usually comes from a guessing game: cook too little and you sell out,
cook too much and food gets thrown away.

**FoodWasteOS** is built for small and mid-sized kitchens — cloud kitchens, cafeterias and
single-outlet restaurants, starting with **Navi Mumbai**.

- **Per-dish demand forecast** for tomorrow, with a prediction band and a measured confidence level.
- **Recommended prep quantity**, rounded to each dish's batch size.
- **Cost of waste** and what following the plan saves.
- **Fast data entry**: daily sales and waste forms plus a forgiving CSV import.

## Features

| Area | Status |
| --- | :---: |
| Daily sales + waste entry, idempotent CSV import with row-level errors | ✅ |
| Dish catalog with batch size and unit cost | ✅ |
| Demand forecasting (weekday baseline, measured confidence, cold-start handling) | ✅ |
| Preparation planner with materialised plans and morning insights | ✅ |
| Dashboard (today, 14-day sold-vs-wasted trend, tomorrow's prep) | ✅ |
| Analytics (waste trend, cost of waste, top wasted dishes, forecast accuracy) | ✅ |
| Supabase Auth JWT verification, tenant scoping, role checks | ✅ |
| Nightly scheduled plan generation (GitHub Actions + secret-protected endpoint) | ✅ |
| Model-run audit trail per generation | ✅ |
| Random Forest challenger + walk-forward backtesting harness | 🧪 experimental, not default |
| Random Forest as default, notifications, billing | ⏳ not yet |

### Screens

| Screen | Purpose |
| --- | --- |
| **Dashboard** | Today at a glance, 14-day sold-vs-wasted trend, tomorrow's prep |
| **Sales entry** | Record sales, prepared quantity and waste, or upload a CSV |
| **AI Preparation Planner** | Tomorrow's per-dish forecast, confidence and recommended quantity |
| **Analytics** | Waste trend, cost of waste, top wasted dishes, forecast accuracy |

## Architecture

```
React SPA (Vite + TypeScript + Tailwind + React Query + Recharts)
        │  HTTPS / JSON — Supabase access token as Bearer
        ▼
FastAPI modular monolith
  api/v1   → routers (thin, schema-validated)
  services → catalog, sales, waste, forecasting, model runs, evaluation, analytics
  ml       → features, baseline, rf, evaluate, registry (in-process)
        │  SQLAlchemy 2.0, one session per request
        ▼
PostgreSQL (Supabase in production · SQLite for tests and local demo)
```

**Design decisions worth knowing**

- **Materialised forecasts.** Plans are stored in a `forecasts` table keyed by
  `(food_item_id, target_date)`, so the morning plan is stable, auditable and cheap to re-read.
  Generation is idempotent — re-running it updates rows instead of duplicating them.
- **Structural multi-tenancy.** Every business table carries `restaurant_id` and every query filters
  on it. Row-level security is documented as defence in depth.
- **Safe re-imports.** `daily_sales` is unique per `(restaurant, dish, date)` and imports upsert, so
  uploading the same file twice is harmless.
- **Stockouts are first-class.** `prepared_quantity` and `stockout` are stored because sales alone
  ignore unsold food, and stockout days hide true demand.
- **Waste can be recorded in parts.** `food_waste` is unique per `(restaurant, dish, date, reason)`.

### Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, React Router, Recharts |
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic v2, Uvicorn |
| ML | pandas, NumPy, scikit-learn, joblib |
| Database & Auth | PostgreSQL and Auth via Supabase (SQLite for local demo/tests) |
| Infra | Docker Compose, Vercel (web), Render (API) |

## How the forecast works

```mermaid
flowchart LR
    A[daily_sales history] --> B[Weekday baseline<br/>recency-weighted avg]
    B --> C[Prediction]
    B --> D[Residual spread]
    D --> E[Prediction band<br/>service level 0.85]
    C --> F[Recommendation<br/>clamped 1.0–1.25× · rounded to batch]
    E --> F
    D --> G[Confidence<br/>high / medium / low]
```

1. **History** is read from `daily_sales` per dish (`quantity_sold`, `prepared_quantity`, stockout flags).
2. **Baseline.** History is grouped by weekday and averaged with recency weighting (decay `0.9`, up to
   8 weeks). That is the prediction.
3. **Band.** The spread of residuals around the average becomes the prediction band, sized by the
   service level (`FORECAST_SERVICE_LEVEL`, default `0.85`).
4. **Recommendation.** It targets the upper band but is clamped to `1.0–1.25 × prediction` and
   rounded up to the dish's batch size, so a noisy week cannot produce an absurd prep number.
5. **Confidence** is derived from measured dispersion and sample size, not assigned by hand. Dishes
   with fewer than 7 observations are returned as `collecting_data` (with their observation count)
   instead of a fabricated number. Stockout-censored history caps confidence at `low`.

### Random Forest challenger

`app/ml/rf.py` trains a Random Forest per tenant on lag, rolling and calendar features. It is compared
against the baseline using **walk-forward (rolling-origin) backtesting** in `app/ml/evaluate.py`.
Random splits are never used, because they leak the future into training. The forest stays a
challenger until it beats the baseline on real tenant history.

## Quickstart

### Option 1 — Docker Compose (Postgres + API + web)

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
| --- | --- |
| Web app | http://localhost:5173 |
| API | http://localhost:8000 |
| Interactive API docs | http://localhost:8000/docs |

The database is initialised from `supabase/schema.sql`. With `SEED_DEMO_DATA=true`, the API seeds a
demo restaurant with 8 dishes and ~11 weeks of sales.

### Option 2 — Local, without Docker

**Backend** (Python 3.12)

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env   # or export the variables yourself

# Choose one database:
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/foodwasteos
export DATABASE_URL=sqlite+pysqlite:///./demo.db     # zero-setup demo

uvicorn app.main:app --reload --port 8000
```

**Frontend** (Node 22)

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

### Configuration

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development` \| `test` \| `staging` \| `production` |
| `AUTH_MODE` | `dev` (demo tenant, local only) or `supabase` (verify JWTs) |
| `DATABASE_URL` | SQLAlchemy URL (`postgresql+psycopg://…` in production) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
| `SEED_DEMO_DATA` | Seed the demo restaurant on startup |
| `SUPABASE_URL` / `SUPABASE_JWT_AUD` | JWKS discovery and audience for token verification |
| `SUPABASE_JWT_SECRET` | Only for legacy HS256 projects; leave empty to use JWKS |
| `FORECAST_SERVICE_LEVEL` | Band width target (default `0.85`) |
| `FORECAST_HISTORY_DAYS` | Lookback window (default `180`) |
| `PLAN_STALE_HOURS` | Age after which a stored plan is flagged stale (default `36`) |
| `CRON_SECRET` | Shared secret for `POST /cron/generate`; empty disables it |
| `ML_ARTIFACT_DIR` | Where trained models are stored locally (registry not yet wired) |

The frontend reads `VITE_API_URL`, `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.

> [!NOTE]
> **Demo mode.** With `AUTH_MODE=dev`, every request resolves to a seeded demo tenant and the UI shows
> a "demo mode" banner. The app **refuses to start** with `AUTH_MODE=dev` in staging or production —
> real deployments must verify Supabase tokens.

## API

All endpoints live under `/api/v1` and require a bearer token (except `/health` and the
secret-protected `/cron/generate`). Interactive docs are served at `/docs` when the API is running.
Payload shapes and examples are in [`docs/API.md`](docs/API.md).

| Area | Endpoints |
| --- | --- |
| **Profile** | `GET /me` |
| **Dishes** | `GET /food-items` · `POST /food-items` · `PATCH /food-items/{id}` |
| **Sales** | `GET /sales` · `POST /sales` · `POST /sales/import` · `GET /sales/template.csv` |
| **Waste** | `GET /waste` · `POST /waste` |
| **Forecasts** | `GET /forecasts/plan?target_date=YYYY-MM-DD` · `POST /forecasts/generate` · `GET /forecasts/accuracy?days=28` |
| **Scheduled** | `POST /cron/generate` (all tenants; `X-Cron-Secret`, no user token) |
| **Insights** | `GET /dashboard` · `GET /analytics/summary?days=30` |

**Role checks:** creating or editing dishes, importing CSVs and regenerating plans require the
`owner` or `manager` role.

**CSV import** accepts flexible headers (`sold` / `quantity_sold`, `prepared` / `prepared_quantity`,
`date` / `sale_date`) and reports per-row errors without rejecting the whole file. Unknown dishes are
created automatically, so a first upload is never blocked. A ready-made template is available at
`GET /sales/template.csv`.

## Data model

`restaurants` · `users` · `food_items` · `daily_sales` · `food_waste` · `forecasts` · `model_runs`

The canonical DDL is in [`supabase/schema.sql`](supabase/schema.sql); the reasoning behind the
model is in [`docs/07-architecture.md`](docs/07-architecture.md).

## Testing

```bash
# Backend
cd backend && .venv/bin/python -m pytest -q

# Frontend
cd frontend && npm run typecheck && npm run build
```

The backend suite covers idempotent upserts, partial-success CSV import, plan generation,
cold-start behaviour, waste cost maths and the waste-rate formula, auth/role/tenancy isolation,
scheduled generation, model-run auditing, the recommendation formula, band and confidence output,
walk-forward metrics, and the no-leakage guarantee for rolling features.

CI (`.github/workflows/ci.yml`) runs pytest, `tsc --noEmit` and `vite build` on every push and PR.

## Project layout

```
FoodWasteOS/
├── backend/
│   ├── app/
│   │   ├── api/         # deps, v1 routers
│   │   ├── core/        # settings, JWT verification, request identity
│   │   ├── db/          # models, session, demo seed
│   │   ├── ml/          # features, baseline, random forest, evaluation, registry
│   │   ├── schemas/     # Pydantic contracts
│   │   └── services/    # catalog, sales, waste, forecasting, model runs, evaluation, analytics
│   ├── tests/
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── components/  # layout, stat cards, shared bits
│       ├── lib/         # API client, Supabase client, formatters
│       └── pages/       # dashboard, planner, sales entry, analytics, login
├── supabase/
│   └── schema.sql       # canonical database schema
├── docs/
│   ├── 01-prd.md … 10-readme.md  # product, flows, stack, schema, architecture, plan
│   └── API.md           # endpoint contract and payload examples
└── docker-compose.yml
```

## Deployment

| Component | Platform | Notes |
| --- | --- | --- |
| **Web** | Vercel | `npm run build`, output directory `dist/` |
| **API** | Render | Web service built from `backend/Dockerfile`; health check on `/health` |
| **Database + Auth** | Supabase | Session pooler for serverless, direct connection from Render |

Apply `supabase/schema.sql` before the first deploy. Run a single API instance with in-process ML, or
move generation to a scheduled job as the number of tenants grows.

## Roadmap

- [ ] Collect 4–6 weeks of real sales per pilot outlet, then judge the forest against the baseline
      with the existing backtest harness before switching the default.
- [ ] Morning digest (email / WhatsApp) driven by the same insights the planner shows.
- [ ] Stockout-aware demand correction once `stockout` flags accumulate.
- [ ] Per-dish substitution and festival effects — only when the data supports them.
- [ ] Notifications and billing.
