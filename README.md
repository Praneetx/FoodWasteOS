# FoodWasteOS

Preparation intelligence for restaurants: predicts tomorrow's demand per dish, recommends how
much to prepare, and shows what that plan saves. Built for small and mid-sized kitchens — cloud
kitchens, cafeterias and single-outlet restaurants in Navi Mumbai first.

The core question is not "how do we cook less?" but "how do we prepare the right amount?" — enough
to avoid selling out, not so much that food is thrown away.

## What is implemented

| Area | Status |
| --- | --- |
| Daily sales + waste entry, idempotent CSV import with row-level errors | done |
| Dish catalog with batch size and unit cost | done |
| Demand forecasting (weekday baseline, measured confidence, cold-start handling) | done |
| Preparation planner with materialised plans and morning insights | done |
| Dashboard (today, 14-day sold-vs-wasted trend, tomorrow's prep) | done |
| Analytics (waste trend, cost of waste, top wasted dishes, forecast accuracy) | done |
| Random Forest challenger + walk-forward backtesting harness | done (experimental, not default) |
| Supabase Auth JWT verification, tenant scoping, role checks | done |
| Random Forest promoted to default, notifications, billing | not yet |

Three screens ship first, as specified: **Dashboard**, **Sales entry**, **AI Preparation Planner**,
with **Analytics** alongside them.

## Architecture at a glance

```
React SPA (Vite + TS + Tailwind + React Query + Recharts)
        │  HTTPS / JSON, Supabase access token as Bearer
        ▼
FastAPI modular monolith
  api/v1  → routers (thin, schema-validated)
  services → catalog, sales, waste, forecasting, analytics
  ml       → features, baseline, rf, evaluate, registry (in-process)
        │  SQLAlchemy 2.0, one session per request
        ▼
PostgreSQL (Supabase in production, SQLite for tests and local demo)
```

Forecasts are **materialised** in a `forecasts` table keyed by `(food_item_id, target_date)`, so the
morning plan is stable, auditable and cheap to re-read. Generation is idempotent: re-running it for
the same date updates rows instead of duplicating them.

Full detail — decisions, data model rationale, ML rules, confidence semantics, API surface,
security, deployment and scaling — is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The endpoint
contract lives in [docs/API.md](docs/API.md).

## How the forecast works

1. History is read from `daily_sales` per dish (`quantity_sold`, `prepared_quantity`, stockout flags).
2. The baseline groups history by weekday and takes a recency-weighted average (decay 0.9, up to
   8 weeks). That is the prediction.
3. The spread of residuals around that average becomes the prediction band, sized by the service
   level (`FORECAST_SERVICE_LEVEL`, default 0.85).
4. The recommendation targets the upper band but is clamped to `1.0–1.25 × prediction` and rounded
   up to the dish's batch size, so a noisy week cannot produce an absurd prep number.
5. Confidence is derived from measured dispersion and sample size, not assigned by hand. Dishes with
   fewer than 7 observations are returned as `collecting_data` with their observation count instead
   of a fabricated number. Stockout-censored history caps confidence at `low`.

The Random Forest (`app/ml/rf.py`) is trained per tenant on lag/rolling/calendar features and is
compared against the baseline with walk-forward (rolling-origin) backtesting in `app/ml/evaluate.py`.
Random splits are never used — they leak the future into training. The forest stays a challenger
until it beats the baseline on real tenant history.

## Quickstart

### Docker Compose (Postgres + API + web)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Web: http://localhost:5173

The database is initialised from `supabase/schema.sql` and the API seeds a demo tenant with 8 dishes
and ~11 weeks of sales when `SEED_DEMO_DATA=true`.

### Local, no Docker

Backend:

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env   # or export the variables yourself

# Postgres
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/foodwasteos
# ...or a zero-setup SQLite demo database
export DATABASE_URL=sqlite+pysqlite:///./demo.db

uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

### Environment

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development` \| `test` \| `staging` \| `production` |
| `AUTH_MODE` | `dev` (demo tenant, local only) or `supabase` (verify JWTs) |
| `DATABASE_URL` | SQLAlchemy URL (`postgresql+psycopg://…` in production) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
| `SEED_DEMO_DATA` | Seed the demo restaurant on startup |
| `SUPABASE_URL` / `SUPABASE_JWT_AUD` | JWKS discovery and audience for token verification |
| `SUPABASE_JWT_SECRET` | Only for legacy HS256 projects; leave empty to use JWKS |
| `FORECAST_SERVICE_LEVEL` | Band width target, default `0.85` |
| `FORECAST_HISTORY_DAYS` | Lookback window, default `180` |
| `ML_ARTIFACT_DIR` | Where trained models are stored locally |

The frontend reads `VITE_API_URL`, `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.

> **Demo mode:** with `AUTH_MODE=dev` every request is resolved to a seeded demo tenant and the UI
> shows a yellow "demo mode" banner. The app refuses to start with `AUTH_MODE=dev` in
> staging/production — real deployments must verify Supabase tokens.

## Data model

Five product tables, plus a forecast cache and a model-run log:

`restaurants` · `users` · `food_items` · `daily_sales` · `food_waste` · `forecasts` · `model_runs`

Canonical DDL: [`supabase/schema.sql`](supabase/schema.sql). Notable choices, all explained in the
architecture doc:

- Every business table carries `restaurant_id`; every query filters on it, so tenancy is structural
  rather than a convention. RLS is documented as defence in depth.
- `daily_sales` is unique per `(restaurant, dish, date)`, and imports upsert — re-uploading a file is
  safe.
- `prepared_quantity` and `stockout` are first-class, because sales without prep ignore unsold food
  and stockout days hide demand.
- `food_waste` is unique per `(restaurant, dish, date, reason)`, so waste can be recorded in parts.

## API

All endpoints are under `/api/v1` and require a bearer token (except `/health`):

```
GET    /me
GET    /food-items                 POST /food-items            PATCH /food-items/{id}
GET    /sales                      POST /sales                 POST /sales/import
GET    /sales/template.csv         GET  /waste                 POST /waste
GET    /forecasts/plan?target_date=YYYY-MM-DD
POST   /forecasts/generate
GET    /forecasts/accuracy?days=30
GET    /dashboard                  GET  /analytics/summary?days=30
```

Examples and payload shapes: [docs/API.md](docs/API.md).

CSV import accepts flexible headers (`sold`/`quantity_sold`, `prepared`/`prepared_quantity`,
`date`/`sale_date`) and reports per-row errors without rejecting the file. Unknown dishes are
created automatically so a first upload is never blocked.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q        # 13 tests
cd frontend && npm run typecheck && npm run build
```

The suite covers idempotent upserts, partial-success CSV import, plan generation and stability,
cold-start behaviour, waste cost maths, the recommendation formula, band/confidence output,
walk-forward metrics and the no-leakage guarantee for rolling features.

## Project layout

```
backend/
  app/
    api/          deps, v1 routers
    core/         settings, JWT verification, request identity
    db/           models, session, demo seed
    ml/           features, baseline, random forest, evaluation, registry
    schemas/      Pydantic contracts
    services/     catalog, sales, waste, forecasting, analytics
  tests/
frontend/
  src/
    components/   layout, stat cards, shared bits
    lib/          API client, Supabase client, formatters
    pages/        dashboard, planner, sales entry, analytics, login
supabase/schema.sql
docs/ARCHITECTURE.md · docs/API.md
```

## Deployment

- **Web** → Vercel (`npm run build`, output `dist/`).
- **API** → Render web service built from `backend/Dockerfile`; run one instance with in-process
  ML, or move generation to a scheduled job as tenants grow.
- **Database + Auth** → Supabase Postgres (session pooler for serverless, direct connection from
  Render) and Supabase Auth.
- Run `uvicorn app.main:app` behind the platform's health check on `/health`; apply
  `supabase/schema.sql` before first deploy.

## Next steps after the pilot

1. Collect 4–6 weeks of real sales per pilot outlet, then judge the forest against the baseline
   using the existing backtest harness before switching the default.
2. Add a morning digest (email/WhatsApp) driven by the same insights the planner shows.
3. Add stockout-aware demand correction once `stockout` flags accumulate.
4. Add per-dish substitution/festival effects only when the data supports them.
