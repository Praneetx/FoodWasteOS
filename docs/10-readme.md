# FoodWasteOS

Preparation intelligence for restaurants: predicts tomorrow's demand per dish, recommends how much
to prepare, and shows what that plan saves. Built for small and mid-sized kitchens — cloud kitchens,
cafeterias and single-outlet restaurants in Navi Mumbai first.

The core question is not "how do we cook less?" but **"how do we prepare the right amount?"** —
enough to avoid selling out, not so much that food is thrown away.

> This README is the entry point for the documentation set in `docs/`. The repository-level
> [README.md](../../README.md) remains the original concise overview.

---

## 1. Status

| Area | State |
|---|---|
| Daily sales entry, idempotent CSV import with row-level errors | Shipped |
| Dish catalog with batch size and unit cost | Shipped |
| Waste recording (list + upsert by reason) | Shipped |
| Demand forecasting (weekday baseline, measured confidence, cold start) | Shipped |
| Preparation planner with materialised plans and morning insights | Shipped |
| Dashboard (today, 14-day sold-vs-wasted, tomorrow's prep) | Shipped |
| Analytics (waste trend, waste cost, top wasted dishes, forecast accuracy) | Shipped |
| Random Forest challenger + walk-forward backtesting | Experimental (tests only, not served) |
| Supabase Auth JWT verification, tenant scoping, role checks | Shipped |
| Waste entry screen | Shipped |
| Nightly scheduled generation | Shipped (GitHub Actions + `X-Cron-Secret`) |
| Model-run audit trail | Shipped (`model_runs` row per generation) |
| Notifications, billing | Not yet |

Four screens ship: **Dashboard**, **Sales entry**, **AI Preparation Planner**, **Analytics**, plus
**Login** when Supabase is configured.

---

## 2. Architecture at a glance

```
React SPA (Vite + TS + Tailwind + React Query + Recharts)
        │  HTTPS / JSON, Supabase access token as Bearer
        ▼
FastAPI modular monolith
  api/v1   → thin routers (validation + identity)
  services → catalog, sales, waste, forecasting, analytics
  ml       → features, baseline, rf, evaluate, registry (in-process)
        │  SQLAlchemy 2.0, one session per request
        ▼
PostgreSQL (Supabase in production, SQLite for tests and local demo)
```

Forecasts are **materialised** in `forecasts` keyed by `(food_item_id, target_date)`, so the morning
plan is stable, auditable and cheap to re-read. Generation is idempotent: re-running it for the same
date updates rows instead of duplicating them.

Full detail: [architecture](07-architecture.md) · [backend](05-backend-structure.md) ·
[data model](08-data-model.md) · [schema](06-database-schema.md).

---

## 3. How the forecast works

1. History is read from `daily_sales` per dish (`quantity_sold`, `prepared_quantity`, stockout flags).
2. The baseline groups history by weekday and takes a recency-weighted average (decay 0.9, up to
   8 weeks). That is the prediction.
3. The spread of same-weekday observations becomes the prediction band, sized by the service level
   (`FORECAST_SERVICE_LEVEL`, default 0.85 → z ≈ 1.04).
4. The recommendation targets the upper band, is clamped to ≤1.25× prediction and ≥ prediction, and
   is rounded up to the dish's batch size.
5. Confidence is derived from measured dispersion and sample size, not assigned by hand. Dishes with
   fewer than 7 observations return `collecting_data` with their observation count instead of a
   fabricated number. Stockout-censored history caps confidence at `low`.

The Random Forest is trained per tenant on lag/rolling/calendar features and compared against the
baseline with walk-forward (rolling-origin) backtesting. Random splits are never used. It stays a
challenger until it beats the baseline on real tenant history.

---

## 4. Quickstart

### Docker Compose (Postgres + API + web)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000 (OpenAPI at `/docs`)
- Web: http://localhost:5173

The database is initialised from `supabase/schema.sql`, and the API seeds a demo tenant with 8 dishes
and 77 days of sales when `SEED_DEMO_DATA=true` in development.

### Local, no Docker

Backend (Python 3.12):

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env

# Postgres
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/foodwasteos
# ...or a zero-setup SQLite demo database
export DATABASE_URL=sqlite+pysqlite:///./demo.db

uvicorn app.main:app --reload --port 8000
```

Frontend (Node 22):

```bash
cd frontend
npm install
npm run dev          # Vite proxies /api to localhost:8000
```

Set `VITE_API_URL=http://localhost:8000` only if you are not using the dev proxy.

### Demo mode

With `AUTH_MODE=dev` the API resolves every request to the seeded demo tenant. The UI runs without
login when `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` are unset and shows a yellow "demo mode"
banner. The API refuses to start with `AUTH_MODE=dev` in staging/production.

---

## 5. Environment

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` \| `test` \| `staging` \| `production` |
| `AUTH_MODE` | `dev` (demo tenant, local only) or `supabase` (verify JWTs) |
| `DATABASE_URL` | SQLAlchemy URL (`postgresql+psycopg://…` in production) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
| `SEED_DEMO_DATA` | Seed the demo restaurant on startup (development only) |
| `SUPABASE_URL` / `SUPABASE_JWT_AUD` | JWKS discovery and audience for token verification |
| `SUPABASE_JWT_SECRET` | Legacy HS256 projects only; leave empty to use JWKS |
| `FORECAST_SERVICE_LEVEL` | Band width target, default `0.85` |
| `FORECAST_HISTORY_DAYS` | Lookback window, default `180` |
| `FORECAST_MIN_OBSERVATIONS` | Cold-start cutoff, default `7` |
| `PLAN_STALE_HOURS` | Age after which a plan is stale, default `36` |
| `ML_ARTIFACT_DIR` | Model artifact directory (registry not yet wired) |
| `MAX_CSV_BYTES` | Upload limit, default `5_000_000` |
| `CRON_SECRET` | Shared secret for `POST /cron/generate`; empty disables it |

Frontend reads `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` and
`VITE_PROXY_TARGET` (dev proxy). Full table: [tech stack](03-tech-stack.md#5-configuration-surface).

---

## 6. Data model

Seven tables: `restaurants` · `users` · `food_items` · `daily_sales` · `food_waste` · `forecasts` ·
`model_runs`. Canonical DDL: [supabase/schema.sql](../../supabase/schema.sql).

Notable choices:

- Every business table carries `restaurant_id`; every query filters on it, so tenancy is structural
  rather than a convention. RLS is documented as defence in depth.
- `daily_sales` is unique per `(dish, date)`; imports upsert, so re-uploading a file is safe.
- `prepared_quantity` and `stockout` are first-class because sales without prep ignore unsold food,
  and stockout days hide demand.
- `food_waste` is unique per `(dish, date, reason)`, so waste can be recorded in parts.
- Plans are unique per `(dish, target_date)` and regenerated in place.

Details and derived metrics: [database schema](06-database-schema.md) ·
[data model](08-data-model.md).

---

## 7. API

All endpoints are under `/api/v1` and require a bearer token (except `/health` and the
secret-protected `/cron/generate`):

```
GET    /me
GET    /food-items                 POST /food-items            PATCH /food-items/{id}
GET    /sales                      POST /sales                 POST /sales/import
GET    /sales/template.csv         GET  /waste                 POST /waste
GET    /forecasts/plan?target_date=YYYY-MM-DD
POST   /forecasts/generate
GET    /forecasts/accuracy?days=28
POST   /cron/generate              (X-Cron-Secret; all tenants)
GET    /dashboard                  GET  /analytics/summary?days=30
```

Role rules: catalogue writes, CSV import and forced generation require `owner` or `manager`. Sales and
waste writes are available to `staff`. Every resource is tenant-scoped.

Payload shapes and examples: [API contract](API.md). Backend conventions:
[backend structure](05-backend-structure.md).

---

## 8. Screens

| Route | Screen | Content |
|---|---|---|
| `/` | Dashboard | Today's sold/waste/cost, tomorrow's prep, 14-day trend |
| `/planner` | Preparation plan | Per-dish predicted/prepare/confidence/range, insights, regenerate |
| `/sales` | Sales & waste entry | CSV import, manual upsert, waste form, catalogue, recent rows |
| `/analytics` | Analytics | Waste trend, cost, top wasted, MAE/WAPE/bias/band coverage |
| `/login` | Login | Supabase email/password (rendered when configured) |

UI conventions: [frontend guidelines](04-frontend-guidelines.md).

---

## 9. Project layout

```
backend/
  app/
    api/          deps, v1 routers
    core/         settings, JWT verification, request identity
    db/           models, session, demo seed
    ml/           features, baseline, random forest, evaluation, registry
    schemas/      Pydantic contracts
    services/     catalog, sales, waste, forecasting, model runs, evaluation, analytics
  tests/          57 tests (SQLite in-memory)
frontend/
  src/
    components/   layout, stat cards, shared bits
    lib/          API client, Supabase client, formatters
    pages/        dashboard, planner, sales entry, analytics, login
supabase/schema.sql
docs/             01–10 specification set + API.md
docker-compose.yml
```

---

## 10. Tests and quality gates

```bash
cd backend && python -m pytest -q          # 57 tests
cd frontend && npm run typecheck && npm run build
```

Coverage includes idempotent upserts, partial-success CSV import, plan generation and stability,
cold-start behaviour, waste cost maths and the waste-rate formula, auth/role/tenancy isolation,
scheduled generation, model-run auditing, the recommendation formula, band/confidence output,
walk-forward metrics and the no-leakage guarantee for rolling features.

Verified in this environment (2026-11-16):

- `pytest` — 57 passed (Python 3.12 via `uv`).
- `npm run typecheck` — passes.
- `npm run build` — passes; 901.3 kB JS (249.5 kB gzip), with Vite's >500 kB chunk warning.
- CI runs the same gates via `.github/workflows/ci.yml`.
- No live browser run was performed.

---

## 11. Deployment

- **Web** → Vercel (`npm run build`, output `dist/`).
- **API** → Render web service built from `backend/Dockerfile`; one instance with in-process ML.
- **Nightly plans** → GitHub Actions (`.github/workflows/nightly-plan.yml`) calls
  `POST /api/v1/cron/generate` with `X-Cron-Secret`; set `API_URL` and `CRON_SECRET` repository secrets.
- **Database + Auth** → Supabase Postgres (session pooler for serverless, direct connection from
  Render) and Supabase Auth.
- Apply `supabase/schema.sql` before first deploy; health check on `/health`.
- Set `APP_ENV=production` and `AUTH_MODE=supabase`; never deploy with dev auth.

---

## 12. Documentation index

| Doc | Contents |
|---|---|
| [01 — PRD](01-prd.md) | Problem, personas, scope, success metrics, user stories |
| [02 — App flow](02-app-flow.md) | Auth, onboarding, entry, plan, analytics, edge cases |
| [03 — Tech stack](03-tech-stack.md) | Versions, rationale, config, tooling |
| [04 — Frontend guidelines](04-frontend-guidelines.md) | Structure, data fetching, design system, patterns |
| [05 — Backend structure](05-backend-structure.md) | Layering, routers, services, schemas, recipes |
| [06 — Database schema](06-database-schema.md) | Tables, constraints, indexes, tenancy, migrations |
| [07 — Architecture](07-architecture.md) | Context, decisions, forecast engine, security, operations |
| [08 — Data model](08-data-model.md) | Entities, invariants, metric definitions, lifecycle |
| [09 — Implementation plan](09-implementation-plan.md) | Status, phases, backlog, test plan, DoD |
| [API contract](API.md) | Endpoint-by-endpoint v1 contract |

---

## 13. Known gaps

1. `ML_ARTIFACT_DIR` and `ml/registry.py` are unwired.
2. The Random Forest is not served; the baseline is always used.
3. No feedback digest (email/WhatsApp) or billing.
4. No Alembic; `schema.sql` is the source of truth.
5. RLS policies exist only as commented examples.
6. No request IDs, structured request logs, error tracking or app-level rate limiting (Phase 2).
7. The JS bundle is ~901 kB and not code-split.

The next steps are prioritised in [09 — Implementation plan](09-implementation-plan.md).

---

## 14. License

No license file is included in this repository. Treat it as proprietary until one is added.
