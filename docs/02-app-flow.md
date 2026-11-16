# FoodWasteOS — Application Flow

How a user moves through the product, what the system does at each step, and how failures are
handled. Screens are described in [04-frontend-guidelines.md](04-frontend-guidelines.md); the
underlying services are in [05-backend-structure.md](05-backend-structure.md).

---

## 1. Actors and entry points

| Actor | Enters via | Can do |
|---|---|---|
| Owner / manager | Supabase login → SPA | Everything: catalogue, import, entry, plan generation, analytics |
| Staff | Supabase login → SPA | Sales and waste entry, read plans/dashboard |
| Demo user | No login (Supabase env unset) | Everything as demo owner, against seeded sample data |
| Scheduler (future) | `POST /api/v1/forecasts/generate` | Generate plans nightly |

Routes:

| Path | Screen | Guard |
|---|---|---|
| `/login` | Login (rendered by `App` when Supabase is configured and no session) | none |
| `/` | Dashboard | session (or demo mode) |
| `/planner` | Preparation plan | session (or demo mode) |
| `/sales` | Sales & waste entry, catalogue, recent sales | session (or demo mode) |
| `/analytics` | Waste and accuracy analytics | session (or demo mode) |
| `*` | Redirect to `/` | — |

There is no sign-up or password-reset screen in v0; accounts are provisioned during onboarding.
A sign-out control lives in the sidebar and mobile header, and an expired session returns the user to
login with an explanatory notice.

---

## 2. Boot and authentication flow

```mermaid
flowchart TD
  A[Browser loads SPA] --> B{Are VITE_SUPABASE_URL and ANON_KEY set?}
  B -- No --> C[Demo mode: skip login, show amber banner]
  B -- Yes --> D[supabase.auth.getSession]
  D --> E{Session?}
  E -- No --> F[Render LoginPage]
  F --> G[signInWithPassword]
  G --> H{Success?}
  H -- No --> F
  H -- Yes --> I[onAuthStateChange sets session]
  E -- Yes --> I
  I --> J[Layout + route content]
  C --> J
  J --> K[API client attaches Bearer token]
  K --> L{API responds 401?}
  L -- Yes --> M[Dispatch foodwasteos:unauthorized]
  M --> N[App clears session -> LoginPage]
  L -- No --> O[Normal render]
```

Backend resolution:

1. `AUTH_MODE=dev` → every request resolves to the demo tenant (`demo@foodwasteos.local`,
   `Spice Route Kitchen`). The app refuses to start with dev auth in `staging`/`production`.
2. `AUTH_MODE=supabase` → verify JWT (JWKS ES256/RS256, or HS256 secret for legacy projects),
   `aud` and `exp`; then look up the app `users` row by `sub`.
3. No token → 401. Valid token but no provisioned profile → 403.
4. Every subsequent query is scoped by `restaurant_id` from that profile.

Demo mode contract: the **frontend** decides to skip login when Supabase env vars are missing; the
**backend** must be running `AUTH_MODE=dev`. Mixing one without the other produces a banner with 401s,
which is visible rather than silent.

---

## 3. Flow A — First-time onboarding and historical import

Goal: get from zero data to a usable plan.

```mermaid
sequenceDiagram
  actor M as Manager
  participant Web as SPA (/sales)
  participant API as FastAPI
  participant DB as Postgres

  M->>Web: Open Sales screen
  Web->>API: GET /food-items
  API->>DB: select active items for tenant
  API-->>Web: [] (empty)
  M->>Web: Download template (optional)
  Web->>API: GET /sales/template.csv
  API-->>Web: CSV template
  M->>Web: Choose CSV + Upload
  Web->>API: POST /sales/import (multipart)
  API->>API: parse, alias columns, validate rows
  API->>DB: create missing dishes
  API->>DB: upsert daily_sales (dedupe last-wins)
  API-->>Web: {imported, items_created, skipped, errors[]}
  Web->>Web: show report, invalidate sales/items/dashboard/plan/analytics
  M->>Web: Open Dashboard
  Web->>API: GET /dashboard
  API->>API: generate tomorrow's plan if missing
  API-->>Web: today + 14-day series + tomorrow totals
```

Rules the user experiences:

- A 90-day file with a few bad rows still imports the good ones. Bad rows are listed by spreadsheet
  row number (header = row 1).
- Header names are forgiving; required semantics are date, dish, quantity sold.
- Unknown dishes appear in `items_created` with batch size 1, so they are immediately plannable after
  7 days of history.
- Uploading the same file again is safe; it updates instead of duplicating.
- Max file size 5 MB (`MAX_CSV_BYTES`), role owner/manager only.

Failure states:

| Condition | User sees |
|---|---|
| Empty file / unparseable CSV | 400 "empty file" or "could not parse CSV" |
| Missing required columns | 400 listing missing columns |
| File > 5 MB | 413 |
| Some rows invalid | Success banner with "N skipped" and row errors |
| Staff role | 403 "requires role: owner, manager" |

---

## 4. Flow B — Daily manual entry

```mermaid
sequenceDiagram
  actor S as Staff
  participant Web as SPA (/sales)
  participant API as FastAPI
  participant DB as Postgres

  S->>Web: Select dish, date, sold, prepared (optional)
  S->>Web: Tick promotion / sold out if relevant
  Web->>API: POST /sales
  API->>API: verify dish belongs to tenant (404 otherwise)
  API->>DB: upsert daily_sales (unique dish+date)
  API-->>Web: SaleOut
  Web->>Web: clear inputs, invalidate sales/dashboard/plan/analytics
  S->>Web: Optional: add a new dish (name, batch, cost)
  Web->>API: POST /food-items
  API-->>Web: 201 or 409 duplicate name
```

Notes:

- Re-saving the same dish/date updates the row (no duplicates) — useful for corrections.
- `prepared_quantity` is optional; the UI surfaces it because it is required for true waste-rate
  analysis and stockout interpretation.
- The "sold out" flag matters: it tells the system that sales understate demand.
- Waste entry is a separate form on the Sales screen (dish, date, quantity, reason, notes), with a
  recent-waste list beside recent sales. Saving invalidates dashboard, analytics, plan and accuracy.
- Catalogue changes are owner/manager only; a staff member will see 403 on dish creation.

---

## 5. Flow C — Viewing the preparation plan (core journey)

```mermaid
sequenceDiagram
  actor O as Owner
  participant Web as SPA (/planner)
  participant API as FastAPI
  participant Svc as forecasting service
  participant DB as Postgres

  O->>Web: Open Planner (default date = tomorrow)
  Web->>API: GET /forecasts/plan?target_date=D
  API->>DB: forecasts where tenant + D
  alt Forecast rows exist
    API->>API: compose plan from stored rows
  else No rows
    API->>DB: load sales history < D (≤180 days)
    loop each active dish
      API->>Svc: weekday_average_forecast(history, D)
      alt < 7 observations
        Svc-->>API: None
      else enough history
        Svc-->>API: predicted, lower, upper, confidence, n
        API->>Svc: recommend_preparation(predicted, upper, batch)
        API->>DB: upsert forecasts row
      end
    end
    API->>DB: delete rows for dishes no longer forecastable
  end
  API-->>Web: plan + insights + stale flag
  Web-->>O: table, totals, confidence badges, insights
  O->>Web: Regenerate
  Web->>API: POST /forecasts/generate {target_date, force:true}
  API->>Svc: recompute all active dishes
  API-->>Web: fresh plan
```

What the owner decides from the screen:

- **Prepare** quantity per dish (already clamped and batch-rounded).
- **Confidence** per dish: high/medium/low; low items are explicitly "a starting point".
- **Typical range** (lower–upper) to judge risk.
- **Last week** number as a sanity check.
- **What changed**: total prep, demand vs a usual weekday, count of low-confidence and
  collecting-data dishes.

Edge cases:

| Situation | Behaviour |
|---|---|
| New dish, < 7 observations | Row present with `status=collecting_data`, `observations=n`, no fake numbers |
| Dish has 7–27 observations | Number produced, confidence likely `low` (needs ≥14 for medium/high) |
| Recent stockout in the dish's history | Confidence capped at `low` |
| Plan older than `PLAN_STALE_HOURS` (default 36 h) | `stale: true`; UI says regenerate |
| Plan generation throws | Router returns 500; dashboard catches and renders without tomorrow's card |
| Dish deactivated | Dropped from plan on next regeneration |
| Date in the past | Allowed; history used is strictly before that date |

Plan reads can write: `GET /forecasts/plan` materialises rows if none exist. This is intentional so
the first open of the day is fast for everyone else, but it means a GET has a side effect.

---

## 6. Flow D — Dashboard

1. SPA requests `GET /dashboard` (query key `["dashboard"]`).
2. API resolves "today" in the restaurant's timezone.
3. It aggregates the last 14 days of sales and waste, computes today's waste rate and cost, then
   attempts to materialise tomorrow's plan (wrapped in try/except).
4. UI shows four stat cards, a 14-day composed chart, and a dark "tomorrow" card linking to the planner.
5. If every series point is zero, an empty state replaces the page with an "Add sales data" CTA.

Dashboard is one call by design: the owner's first screen must not fan out to five endpoints.

---

## 7. Flow E — Analytics and the feedback loop

```mermaid
flowchart LR
  A[Staff records sales + waste daily] --> B[(daily_sales / food_waste)]
  B --> C[Plan generation for date D]
  C --> D[(forecasts)]
  D --> E[Sales for D arrive]
  E --> F[GET /forecasts/accuracy]
  F --> G[MAE / WAPE / bias / band coverage / stockouts]
  G --> H[Owner adjusts trust and prep]
  H --> A
```

Analytics screen:

- Range selector 7d / 30d / 90d drives both `analytics/summary` and `forecasts/accuracy`.
- Accuracy window queries forecasts whose `target_date` is in `[today − days, today)` and joins the
  actual sale row for that dish and date.
- If no forecasts have reached their target date yet, the screen explains that plans become
  comparable only after tomorrow happens — it does not render fake zeros.
- Stockout days are counted as distinct dates in the window with any `stockout=true` row.

The loop is the product promise: every day of data must make tomorrow's plan better or at least
measurable.

---

## 8. Cross-cutting states

| State | Where | Behaviour |
|---|---|---|
| Loading | All screens | Pulse skeleton blocks sized like final content |
| Error | All screens | Rose `ErrorNotice` with API detail; retry by refetch (React Query, 1 retry) |
| Empty (no sales) | Dashboard, Sales, Planner | Explanatory copy + CTA; planner still lists dishes as collecting data |
| Unauthorized (401) | API client | Global event → session cleared → login |
| Demo mode | Layout | Amber banner, desktop and mobile variants |
| Stale plan | Planner | Inline "plan is stale, regenerate" hint |
| Unknown/missing cost | Dashboard, Analytics | Em dash + "add dish costs" hint, never `₹0` |

## 9. Navigation model

- **Desktop (≥ md):** persistent left sidebar (brand, 4 nav items, restaurant footer).
- **Mobile (< md):** sticky top header with brand/date and demo banner, fixed bottom tab bar.
- Content is capped at `max-w-6xl`, with bottom padding on mobile so the tab bar never covers content.

## 10. Sequence summary (happy path, day 1 → day 8)

| Day | User action | System effect |
|---|---|---|
| 1 | Upload 60 days of CSV | Dishes created, sales upserted, import report shown |
| 1 | Open planner | Plan generated for tomorrow; all dishes forecast (≥7 obs) |
| 2 | Enter yesterday's actuals | Sales row upserted; queries invalidated |
| 7 | Open analytics | Accuracy appears for plans whose date has passed |
| 8 | View planner | Confidence reflects measured dispersion from the larger sample |
| ongoing | Correct a number | Same row updated; plan regenerated on next explicit refresh |
