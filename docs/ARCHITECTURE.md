# FoodWasteOS — Architecture

Status: MVP foundation (v0.1) · Audience: solo developer / small team · Scope: first pilot restaurant in Navi Mumbai

---

## 1. Product in one paragraph

FoodWasteOS tells a restaurant **how much of each dish to prepare tomorrow**, based on its own historical
sales. The product is a *Daily Preparation Intelligence Engine*, not a restaurant management system: the
restaurant keeps its existing workflow, uploads or enters sales, and gets a prep plan that balances
availability against waste.

Success is measured on four numbers from a pilot: **MAE**, **forecast accuracy**, **unsold quantity**
and **stockout frequency**. A plan that cuts waste while creating stockouts has failed.

---

## 2. Goals and constraints

| Goal | Consequence for the architecture |
|---|---|
| 3–5 screens, one persona (owner/manager) | Single SPA, no role-specific portals in v0 |
| 10–30 dishes, 30–90 days of history per tenant | Per-tenant in-process training is cheap (<1 s); no distributed ML platform |
| Solo developer, 7-week build | Modular monolith, one deployable API, managed Postgres/Auth |
| Forecasting is the differentiator | ML is a first-class module with backtesting, not a side endpoint |
| Predictions must be explainable | Confidence comes from measured residuals, plans expose the drivers |
| Data is commercially sensitive | Strict tenant isolation on every query; no cross-tenant training |

Non-goals for the MVP: POS/aggregator integrations, payments, inventory/recipe costing, multi-outlet
consolidation, weather data, deep learning, real-time streaming, mobile apps.

---

## 3. System context

```
                         ┌──────────────────────────────┐
                         │        Restaurant staff       │
                         └──────────────┬───────────────┘
                                        │ HTTPS
                    ┌───────────────────▼───────────────────┐
                    │  React SPA (Vercel)                    │
                    │  Dashboard · Sales Entry · Planner ·   │
                    │  Analytics                             │
                    └───────┬───────────────────────┬────────┘
                            │ REST /api/v1          │ login / session
                            │ Bearer JWT            │
                    ┌───────▼───────────────┐   ┌───▼────────────────┐
                    │ FastAPI (Render)      │   │ Supabase Auth      │
                    │ API · services · ML   │   │ (JWT issuer)       │
                    └───────┬───────────────┘   └────────────────────┘
                            │ SQLAlchemy
                    ┌───────▼───────────────┐
                    │ Supabase PostgreSQL   │
                    │ tenant data +         │
                    │ forecasts + runs      │
                    └───────────────────────┘
```

One deployable backend, one database, one auth provider. The forecasting job runs **inside** the API
process (nightly cron hitting an endpoint, or APScheduler in the same service), because per-tenant training
is sub-second at this scale.

---

## 4. Architecture decisions

| # | Decision | Rationale | Revisit when |
|---|---|---|---|
| D1 | **Modular monolith** (FastAPI + SPA), not microservices | One team, one deploy target, shared transactions; ML is in-process | >100 tenants or >2 min forecast jobs |
| D2 | **Synchronous SQLAlchemy 2.0 + psycopg** | Simple, debuggable; FastAPI runs sync routes in a threadpool | Forecast jobs need isolation → move to worker |
| D3 | **Supabase** for Postgres + Auth | Managed backups, JWT, social login later; SQLAlchemy connects directly | Self-hosting / cost limits |
| D4 | **Forecasts are materialized** into `forecasts` | The planner must load instantly and show a stable, auditable plan for the day; recomputation is explicit | Real-time re-forecasting |
| D5 | **Baseline first, then Random Forest** | Historical weekday average is a strong, explainable reference; RF enters only if it beats the baseline on held-out data | Model ladder proven |
| D6 | **Tenant isolation in the data-access layer** (`restaurant_id` scope dependency + query helpers) | Defense in depth, avoids leaking rows through hand-written queries | Enable Postgres RLS as second layer |
| D7 | **Idempotent writes** (`UNIQUE(item, date)`, upsert) | Staff re-upload the same CSV; retries must not duplicate sales | — |
| D8 | **Demand ≠ sales is modelled explicitly** (`stockout`, `prepared_quantity`) | When a dish sells out, sales understate demand; ignoring this biases forecasts downward | Full censored-demand model |
| D9 | **No background queue** | 30 items × 90 days is milliseconds; cron + request-time generation suffices | >5 tenants training concurrently |
| D10 | **Money is optional per dish** (`unit_cost`), analytics degrades to quantities | Forcing cost data blocks onboarding; savings estimate is only shown when cost exists | — |

---

## 5. Repository layout

```
foodwasteos/
├── docs/
│   ├── ARCHITECTURE.md          # this document
│   └── API.md                   # endpoint contract + examples
├── supabase/
│   └── schema.sql               # canonical DDL (tables, constraints, indexes)
├── backend/
│   ├── app/
│   │   ├── main.py              # app factory, CORS, lifespan, routers
│   │   ├── core/                # config, JWT verification, logging
│   │   ├── db/                  # Base, session, ORM models, demo seed
│   │   ├── schemas/             # Pydantic request/response contracts
│   │   ├── api/v1/              # thin HTTP layer (validation + auth only)
│   │   ├── services/            # use cases: CSV import, plan generation, analytics
│   │   └── ml/                  # features, baseline, RF, evaluation, registry
│   ├── tests/                   # unit + API tests (SQLite in-memory)
│   └── requirements.txt
├── frontend/
│   └── src/                     # pages, components, api client, supabase client
├── docker-compose.yml           # Postgres + API + Vite dev server
└── .env.example
```

**Layering rule:** `api → services → (ml | db)`. Routers never contain SQL, ML code never touches HTTP,
services never construct responses directly. This keeps the forecast engine testable without a server and
lets a future worker reuse `services/` and `ml/` unchanged.

---

## 6. Data model

Canonical DDL: [`supabase/schema.sql`](../supabase/schema.sql). ERD:

```
restaurants 1──* users
restaurants 1──* food_items 1──* daily_sales
                             1──* food_waste
                             1──* forecasts
restaurants 1──* model_runs
```

| Table | Purpose | Key constraints |
|---|---|---|
| `restaurants` | Tenant root; timezone, currency, default unit cost | `id` uuid |
| `users` | App profile mirroring `auth.users.id`; role owner/manager/staff | `id` = Supabase `sub`, FK restaurant |
| `food_items` | Dish, unit (`plate`/`kg`), `batch_size` for rounding, `unit_cost` | `UNIQUE(restaurant_id, name)` |
| `daily_sales` | One row per dish per day: `quantity_sold`, optional `prepared_quantity`, `promotion`, `stockout` | `UNIQUE(food_item_id, sale_date)` — enables idempotent upsert |
| `food_waste` | Waste events with reason; multiple rows per dish/day allowed by reason | `UNIQUE(food_item_id, waste_date, reason)` |
| `model_runs` | Training metadata: model type, window, MAE/WAPE/bias, params | Append-only, one per tenant retrain |
| `forecasts` | Materialized plan: predicted demand, p10/p90 bounds, recommended prep, confidence, model | `UNIQUE(food_item_id, target_date)` |

Deviations from the original five-table sketch, and why:

- **`restaurant_id` is denormalized onto `daily_sales` / `food_waste`.** Every tenant query filters by it;
  joining through `food_items` on each request is avoidable and easy to forget.
- **`prepared_quantity`** is required to compute the true waste rate (`waste / prepared`) and to know
  whether a day was censored. It is optional so manual entry stays fast.
- **`forecasts` and `model_runs`** make the plan reproducible and the confidence label auditable. Without
  stored bounds and residuals, "Medium confidence" is a guess.
- **`batch_size`** turns a statistical recommendation (e.g. 87.3 portions) into something a kitchen can
  execute (90 portions if the batch is 5).
- **`unit_cost`** (dish-level, with restaurant default) is the only input needed for the savings estimate.

Waste rate definition used everywhere: `waste / (sales + waste)` when prep is unknown, and
`waste / prepared` when `prepared_quantity` is present.

---

## 7. Request and data flows

### 7.1 Onboarding / historical import

```
CSV upload (multipart)
  → size + MIME check (5 MB)
  → pandas parse + column aliasing
  → per-row validation (date, item, quantity ≥ 0)
  → create missing food items (reported to user)
  → dedupe within file (last row wins)
  → upsert on (food_item_id, sale_date)
  → ImportReport { imported, items_created, skipped, errors[] }
```

Partial success is a feature: a single bad row must not reject a 90-day file. Errors are row-scoped.

### 7.2 Daily prediction (the core path)

```
GET /forecasts/plan?target_date=tomorrow
  → if forecasts exist for (tenant, date): return materialized plan
  → else: load sales history (≤ 180 days) as a DataFrame
        → per active dish: baseline forecast (weekday average, recency-weighted)
        → residual std → p10/p90 bounds → safety buffer
        → recommended = ceil(upper / batch_size) * batch_size, clamped to [0.9×, 1.25×] demand
        → confidence from residual dispersion + sample size
        → upsert forecasts rows, return plan + insights
```

Generation is deterministic and idempotent per `(item, target_date)`; a manual **Generate** button and the
nightly cron both call the same service. The nightly job runs at local 02:00 for the next 1–7 days, so the
owner sees a plan at 9 AM without waiting.

### 7.3 Feedback loop

```
Staff enter actual sales + unsold quantities (UI or CSV)
  → daily_sales / food_waste rows
  → nightly retrain (weekly in v0) writes model_runs + new forecasts
  → GET /forecasts/accuracy compares past forecasts to actuals (MAE, WAPE, bias, stockouts)
  → next plan's confidence reflects the measured error
```

This closes the loop the product promise depends on: every day of data must make tomorrow's plan better
or at least measurable.

---

## 8. Forecasting subsystem

### 8.1 Data contract

Training grain: one row per `(food_item_id, sale_date)` with target `quantity_sold`. Minimums:

| History per dish | Behaviour |
|---|---|
| < 7 days | No forecast; plan shows "collecting data (n/7)" |
| 7–27 days | Weekday average, confidence capped at *low* |
| ≥ 28 days | Weekday average + residual bands; RF eligible |

Cold-start dishes fall back to the restaurant's overall daily average for the same weekday, with *low*
confidence. We never invent a number silently — the plan labels the method.

### 8.2 Features

| Group | Features |
|---|---|
| Lags | `sales[t-1]`, `[t-7]`, `[t-14]`, `[t-28]` (shifted to avoid leakage) |
| Rolling | mean/std over 7 and 28 days, shifted by 1 |
| Calendar | day-of-week (one-hot), is-weekend, month, festival flag |
| Events | `promotion` (recorded per day), stockout flag |
| Item | item identity (one-hot for a shared model; per-item models for baseline) |
| Context | restaurant-level daily total (captures footfall) |

Weather and local events are deliberately deferred until the pilot proves the core signal.

### 8.3 Model ladder

1. **Historical weekday average** (v0, shipped): mean of the same weekday over the last 4–8 weeks,
   exponentially weighted. Interpretable, zero training, immediate value.
2. **Linear regression** (reference): tests whether the feature set carries linear signal.
3. **Random Forest** (recommended challenger): 200–400 trees, `min_samples_leaf` tuned to the item's
   observation count, per-tenant single model with item one-hot.
4. **XGBoost** only after a tenant has >180 days of clean data.

A challenger replaces the baseline **only** if it wins on backtests for that tenant. Model choice is stored
per tenant in `model_runs` and echoed in every plan (`model` field), so results stay attributable.

### 8.4 Backtesting protocol

- **Rolling-origin (walk-forward) split**: train through `t`, predict `t+1..t+7`, roll forward. Never a
  random split — that leaks future information.
- Hold out the last 14–28 days; report MAE, WAPE (`Σ|e| / Σactual`), and **bias** (`mean(pred − actual)`).
- Simulate preparation with the recommended quantities: report **stockout rate** and **waste quantity**
  against the restaurant's actual prep, not just statistical error.
- Guardrails: RF must beat baseline by ≥5% WAPE on ≥2 consecutive windows, otherwise keep baseline.

### 8.5 Recommendation and confidence

```
predicted  = weekday-weighted mean demand
residual σ = std(actual − weekday_mean) over the training window
upper      = predicted + z(service_level) * σ        # 85% service level → z ≈ 1.04
recommended= ceil(clamp(upper, 0.90×predicted, 1.25×predicted) / batch_size) * batch_size
```

The safety buffer is **derived from measured dispersion**, not a fixed 5%. Confidence is then a function of
the relative error, not an arbitrary label:

| Confidence | Rule (per dish) |
|---|---|
| high | ≥ 14 observations and residual CV ≤ 0.12 |
| medium | ≥ 14 observations and CV ≤ 0.25 |
| low | fewer observations, CV > 0.25, cold start, or stockout-censored history |

Confidence is a UI commitment: *low* means "treat this as a starting point", and the planner says why.

### 8.6 Serving, retraining, artifacts

- Inference: in-process, per tenant, ≤30 dishes → target p95 < 2 s including DB reads.
- Cache: `forecasts` rows; `generated_at` shown to the user. Regeneration is cheap and explicit.
- Retraining: nightly job retrains weekly per tenant (`model_runs` row), writes joblib artifact to
  `ML_ARTIFACT_DIR` (local disk in v0; Supabase Storage when API instances scale horizontally).
- Failure mode: if generation fails, the API returns the last materialized plan with a stale marker; it
  never fabricates a plan. If no plan exists, the planner shows a clear error and the upload CTA.

---

## 9. API surface

Full contract with examples: [`docs/API.md`](API.md). Summary:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + DB check |
| GET | `/api/v1/me` | Current user + tenant |
| GET/POST/PATCH | `/api/v1/food-items` | Dish catalogue |
| GET/POST | `/api/v1/sales` | List / upsert daily sales |
| POST | `/api/v1/sales/import` | CSV import with row-level report |
| GET/POST | `/api/v1/waste` | Waste entries |
| GET | `/api/v1/forecasts/plan` | Materialized prep plan (+generate if missing) |
| POST | `/api/v1/forecasts/generate` | Explicit (re)generation |
| GET | `/api/v1/forecasts/accuracy` | Backtest of past plans vs actuals |
| GET | `/api/v1/analytics/summary` | Waste trend, savings, top wasted dishes |
| GET | `/api/v1/dashboard` | One-call dashboard payload |

Conventions: JSON, snake_case, ISO-8601 dates (`YYYY-MM-DD`), integer quantities, money as strings/decimals,
errors as `{"detail": ...}`, all list endpoints tenant-scoped, UTC timestamps with the restaurant's timezone
used only for "today/tomorrow" resolution.

---

## 10. Frontend architecture

- **React 18 + TypeScript + Vite**, Tailwind for styling, React Query for server state, Recharts for charts.
- Routes: `/login`, `/` (dashboard), `/sales`, `/planner`, `/analytics`. Auth guard wraps a shared
  `Layout` (sidebar on desktop, bottom tab bar on mobile).
- Server state lives in React Query only (30 s stale time); no Redux. UI state is local.
- Supabase session supplies the bearer token; the API client injects it and maps 401 → login redirect.
- If Supabase env vars are absent the app runs in **demo mode** against a dev-mode API, with a visible
  banner — never silently unauthenticated.
- Screens map 1:1 to the product spec: dashboard summary, CSV/manual sales entry, prep planner (hero
  screen), analytics (waste trend + accuracy + savings).

---

## 11. Security and multi-tenancy

- **Auth**: Supabase issues JWTs. The API verifies signatures (JWKS, ES256/RS256; legacy HS256 secret
  supported), `aud`, and `exp`, then resolves the app user by `sub`.
- **Tenant scope**: a `CurrentUser` dependency exposes `restaurant_id`; every query helper requires it.
  Writes also verify the referenced `food_item_id` belongs to the tenant (no IDOR).
- **Roles**: `owner`/`manager` can mutate catalogue and import; `staff` can add sales/waste only.
- **RLS**: optional second layer in Supabase using `auth.jwt() ->> 'restaurant_id'`; the API connects with
  a role that bypasses RLS, RLS protects direct client access. Add before opening direct DB access.
- **Input limits**: CSV ≤ 5 MB / 50k rows, pydantic bounds on quantities, `reason`/`role` as enums.
- **Secrets**: only in host env (Render/Vercel). Demo mode is explicit and must be off in production.

---

## 12. Deployment and operations

| Component | Host | Notes |
|---|---|---|
| SPA | Vercel | `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` |
| API | Render (Docker) | `DATABASE_URL`, Supabase JWT settings, `ALLOWED_ORIGINS` |
| DB/Auth | Supabase | schema applied from `supabase/schema.sql`; daily backups |
| Nightly job | Render Cron → `POST /api/v1/forecasts/generate` | service token or internal secret |
| Logs/metrics | Render logs + `model_runs` | health endpoint, forecast failure alerts |

Environments: local (docker-compose), staging (same on free tiers), production. Config is env-only; no
secrets in the repo. Migrations: `schema.sql` is the source of truth for v0; introduce Alembic at the first
pilot schema change.

**Observability**: structured request logs with `restaurant_id`, `duration_ms`; `model_runs` is the model
audit trail; import reports are stored in logs. Alerts: 5xx rate, forecast job failure, import error rate.

---

## 13. Scaling path (deliberately deferred)

| Trigger | Change |
|---|---|
| >50 tenants or >5 min nightly job | Extract `ml` into a worker; queue per-restaurant jobs (RQ/Celery + Redis) |
| POS integrations | Ingestion service + per-source adapters; idempotency keys |
| Direct client DB access | Enable RLS policies, separate API DB role |
| Multiple outlets per brand | `outlets` table between `restaurants` and items; plans per outlet |
| Model per cuisine/tenant clusters | Shared feature store + global model with item embeddings |
| High write volume | Partition `daily_sales` by month; retention policy for raw imports |

The service boundaries above are chosen so these are additive, not rewrites.

---

## 14. Roadmap alignment

| Week | Deliverable | Architecture surface |
|---|---|---|
| 1 | Auth, schema, skeleton, demo seed | `core/security`, `db/models`, `supabase/schema.sql` |
| 2 | CSV import, dashboard | `services/csv_import`, `api/v1/sales`, `/dashboard` |
| 3 | Waste tracking | `api/v1/waste`, analytics aggregations |
| 4 | Forecasting + backtests | `ml/features`, `ml/baseline`, `ml/evaluate` |
| 5 | Prep planner | `services/forecasting`, `/forecasts/plan`, planner UI |
| 6 | Analytics, RF challenger, testing | `ml/rf`, `/forecasts/accuracy`, test suite |
| 7 | Deployment, pilot | Render/Vercel, cron, `model_runs` monitoring |

**Pilot gate:** one restaurant, 30–90 days of data, two weeks of live plans. Continue only if waste falls
without increasing stockouts, and the measured MAE is communicated honestly to the owner.
