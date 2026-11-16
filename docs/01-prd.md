# FoodWasteOS — Product Requirements Document (PRD)

| | |
|---|---|
| Status | Living document — reflects code as of 2026-11-16 |
| Product stage | MVP (v0.1), pre-pilot |
| Primary market | Small and mid-sized kitchens: cloud kitchens, cafeterias, single-outlet restaurants in Navi Mumbai |
| Primary persona | Owner / kitchen manager who orders and plans daily preparation |
| Source of truth | The codebase; this PRD describes intent and scope, implementation status is tracked in [09-implementation-plan.md](09-implementation-plan.md) |

---

## 1. Problem

A restaurant kitchen has to decide, every day, how much of each dish to prepare **before** it knows
how many customers will come. Two failure modes are expensive:

- **Over-preparation** — food is cooked, not sold, and thrown away. Direct cost plus disposal and
  staff effort.
- **Under-preparation (stockout)** — the dish sells out, revenue is lost, and historical sales
  understate real demand, which makes tomorrow's guess worse.

Most small kitchens plan from memory and a rough weekday intuition. They do not have a data
scientist, a POS integration, or a forecasting tool sized for 10–30 dishes and a few dozen days of
history.

The question the product answers is **not** "how do we cook less?" It is **"how do we prepare the
right amount?"** — enough to avoid selling out, not so much that food is wasted.

## 2. Product vision

A daily preparation intelligence engine that sits *alongside* the kitchen's existing workflow:
staff keep entering or uploading sales, and the product returns a concrete, explainable
preparation plan for tomorrow, plus the measured impact of following it.

Non-goal: replacing the restaurant's management system (POS, billing, inventory, recipes).

## 3. Personas and jobs to be done

| Persona | Role in product | Job to be done |
|---|---|---|
| Owner / manager | Plans prep, owns waste and P&L | "Tell me how much of each dish to prepare tomorrow, and why" |
| Kitchen staff | Enters daily numbers | "Let me record what sold and what was prepared in under a minute" |
| Analyst / founder (internal) | Watches model quality | "Is the forecast actually beating the naive baseline on this tenant?" |

There is one shared account role model in the backend: `owner`, `manager`, `staff`.

## 4. Goals

| Goal | How it is met |
|---|---|
| Give a usable plan within the first week of data | Weekday baseline works from 7 observations per dish; cold-start dishes are labelled, never fabricated |
| Be explainable | Confidence comes from measured dispersion; the planner shows drivers, bands and last week's number |
| Respect existing workflows | CSV import with flexible headers + fast manual entry; no forced POS integration |
| Cut waste without creating stockouts | Recommendation targets the upper demand band, clamped and rounded to batch size |
| Keep tenant data isolated | Every table and query is scoped by `restaurant_id` |
| Stay cheap to run | Modular monolith, managed Postgres/Auth, in-process ML |

## 5. Non-goals (MVP)

- POS / aggregator (Swiggy, Zomato) integrations
- Payments or billing
- Inventory and recipe-level costing
- Multi-outlet consolidation
- Weather, festival or local-event signals (deferred until core signal is proven)
- Deep learning, real-time streaming
- Native mobile apps
- Role-specific portals (one SPA, one persona)
- Automatic promotion of the Random Forest model

## 6. Success metrics

Success is measured on four pilot numbers, not on model vanity metrics:

| Metric | Definition | Target direction |
|---|---|---|
| MAE | Mean absolute error of predicted demand vs actual sold | Lower |
| Forecast accuracy | `1 − WAPE` over the evaluation window | Higher |
| Unsold quantity | Units wasted per period | Lower |
| Stockout frequency | Days/dates flagged `stockout` | Must not increase |

**Pilot gate:** continue beyond the pilot only if waste falls *without* increasing stockouts, and the
measured MAE is communicated honestly to the owner.

Supporting product metrics: time to first plan (≤ 15 minutes from CSV upload), plan regeneration
rate, weekly active days of data entry.

## 7. Scope — v0 feature set

| ID | Feature | Status |
|---|---|---|
| F1 | Email/password sign-in via Supabase Auth (accounts provisioned during onboarding) | Shipped (backend + login UI) |
| F2 | Demo mode for local evaluation (dev auth + seeded tenant) | Shipped |
| F3 | Dish catalogue with batch size and optional unit cost | Shipped (create/list/patch API; list + create UI) |
| F4 | Daily sales entry (sold, prepared, promotion, stockout) | Shipped |
| F5 | CSV historical import with row-level error report and auto-created dishes | Shipped |
| F6 | Daily waste recording with reason | Shipped (API + Sales screen form and recent list) |
| F7 | Tomorrow's per-dish preparation plan (materialised, explainable) | Shipped |
| F8 | Dashboard: today's numbers, 14-day sold vs wasted, tomorrow's prep | Shipped |
| F9 | Analytics: waste trend, waste cost, top wasted dishes, forecast accuracy | Shipped |
| F10 | Backtesting harness + Random Forest challenger | Code shipped, experimental (tests only) |
| F11 | Nightly scheduled plan generation | Shipped (secret-protected `/cron/generate` + GitHub Actions) |
| F12 | Morning digest (email/WhatsApp) | Not started |
| F13 | Billing | Not started |
| F14 | Model-run audit trail persisted per tenant | Shipped (`model_runs` row per generation) |

## 8. User stories and acceptance criteria

### US-1 — Import historical sales
*As a manager, I want to upload my sales history so the planner has something to learn from.*

- Accepts a CSV up to 5 MB with at least `date`, `food_item`, `quantity_sold`.
- Flexible headers: `sold`/`qty`/`quantity`, `prepared`/`prepared_qty`, `sale_date`/`date`, `item`/`name`.
- One bad row does not reject the file; the response reports `imported`, `skipped`, and up to 200 row errors.
- Unknown dish names are created automatically (batch size 1) and reported in `items_created`.
- Re-uploading the same file does not duplicate rows (unique on dish + date, upsert).
- Duplicate rows inside one file: last row wins.

### US-2 — Record today's numbers
*As a staff member, I want to enter what sold and what was prepared each day.*

- One entry per dish per day; re-saving updates the row.
- `quantity_sold ≥ 0`; `prepared_quantity` optional.
- Promotion and sold-out flags can be recorded.
- Saving invalidates dashboard/plan/analytics queries so numbers refresh.

### US-3 — Get tomorrow's preparation plan
*As an owner, I want a per-dish quantity I can execute in the kitchen.*

- Plan exists for a chosen date (default: tomorrow in the restaurant's timezone).
- Each dish shows predicted demand, recommended prep, confidence, sample size, last same weekday, and a typical range.
- Dishes with < 7 observations show `collecting_data (n/7)` instead of a number.
- Recommendation is always ≥ predicted demand, ≤ 1.25× predicted, rounded up to batch size.
- Serving the plan twice without regeneration returns identical numbers (materialised).
- Regeneration is explicit and idempotent; a plan older than 36 hours is flagged stale.
- Plan includes plain-language insights ("demand is 12% above a usual Saturday", "2 dishes have low confidence").

### US-4 — See today at a glance
*As an owner, I want one screen that tells me how today is going and what tomorrow needs.*

- Sold today, unsold today, waste rate, estimated waste cost (or an explicit "add dish costs" hint).
- 14-day sold-vs-wasted series.
- Tomorrow's recommended total and predicted total with a vs-usual comparison when available.
- Empty state prompts the first upload when no sales exist.

### US-5 — Measure results
*As an owner, I want to know whether waste is falling and whether the plan is accurate.*

- Range selector 7/30/90 days.
- Units sold, units wasted, waste rate, estimated waste cost, top 5 wasted dishes.
- Weekly sold (bars) vs wasted (line) trend.
- Forecast accuracy: MAE, WAPE, bias, % of actuals inside the predicted band, stockout days, dishes scored.
- If no archived plans exist in the window, an explanatory empty state (not a fake zero).

### US-6 — Manage the dish catalogue
*As a manager, I want to control which dishes are planned and how they are batched.*

- Create dish with name, unit, batch size, optional unit cost.
- Duplicate names are rejected per restaurant (409).
- Patch name/unit/batch/cost/active flag (owner/manager only).
- Inactive dishes drop out of the plan; API can include them with `include_inactive=true`.

### US-7 — Tenant and role safety
*As the operator, I need each restaurant's data to be invisible to others.*

- All reads and writes are scoped to the caller's `restaurant_id`.
- Cross-tenant dish IDs return 404, not another tenant's data.
- `staff` cannot mutate the catalogue, import CSVs, or force plan generation.
- Dev auth mode must be impossible to enable in staging/production (startup check).

## 9. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Forecast history lookback is 180 days by default; generation for date *d* only uses sales strictly before *d*. |
| FR-2 | Weekday baseline uses up to 8 same-weekday observations with recency decay 0.9. |
| FR-3 | Bands derive from measured residual dispersion at an 85% service level (configurable). |
| FR-4 | Confidence: high = ≥14 observations and CV ≤ 0.12; medium = ≥14 observations and CV ≤ 0.25; otherwise low. Stockout-censored recent history caps confidence at low. |
| FR-5 | Plans are persisted per `(food_item_id, target_date)`; regeneration updates in place and removes rows for dishes no longer forecastable. |
| FR-6 | Waste rate shown to users = `waste / (sales + waste)` in both dashboard and analytics. This is the final pilot definition (P1.4); a prepared-based rate is out of scope because `prepared_quantity` is optional. |
| FR-7 | Waste cost uses dish unit cost, falling back to the restaurant default; if no cost exists anywhere, the UI shows "—". |
| FR-8 | Accuracy joins materialised forecasts to actual sales for the target date and reports MAE/WAPE/bias/band coverage. |
| FR-9 | CSV import and catalogue mutations require owner/manager. |
| FR-10 | The API never fabricates a plan when history is insufficient; it labels the dish as collecting data. |

## 10. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | Plan endpoint p95 < 2 s for ≤ 30 dishes including DB reads; dashboard one call |
| Availability | Health check reports DB status; dashboard renders even if tomorrow's plan fails |
| Security | JWT verified (JWKS ES256/RS256 or legacy HS256); tenant scope on every query; no secrets in repo |
| Privacy | No cross-tenant training; sales data stays in the tenant's schema rows |
| Explainability | Every plan item carries method, sample size, bounds and confidence |
| Portability | Postgres in production; SQLite works for tests and local demo |
| Operability | Single deployable API; explicit regeneration; `/health` for platform checks |

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Too little history at onboarding | Useless first plans | CSV backfill; cold-start labels; weekday baseline needs only 7 points |
| Garbage in (missing days, no stockout flags) | Biased forecasts | Import validation, explicit stockout flag, no-leakage features, honest confidence |
| Owner distrusts a black box | Low adoption | Show drivers, bands, last same weekday, and measured accuracy |
| Waste falls but stockouts rise | Pilot failure | Recommendation targets upper band; stockout days reported next to accuracy |
| Timezone drift in "today/tomorrow" | Wrong target date | Restaurant timezone used server-side; frontend sends explicit dates |
| Single instance + long training | Timeouts | Per-tenant in-process fit is sub-second at MVP scale; worker deferred |
| Direct DB access leaks rows | Data breach | API-only access today; RLS documented as defence in depth |

## 12. Open questions

1. Should waste entry get its own screen, or be folded into the sales form as an optional field?
2. ~~Is `prepared_quantity` reliable enough in practice to switch waste-rate math to `waste / prepared`?~~
   Resolved 2026-11-16: no — it is optional, so the pilot stays on `waste / (sales + waste)`.
3. What is the minimum sample size before promoting the Random Forest per tenant (currently ≥5% WAPE win on ≥2 windows, per architecture doc)?
4. Do pilot outlets want a printable plan, or is the phone view sufficient?
5. Should the nightly job be a platform cron hitting `/forecasts/generate`, or APScheduler inside the API?

## 13. Release criteria (pilot)

- [x] Tenant-scoped auth with roles
- [x] CSV import, manual entry, catalogue
- [x] Materialised daily plan with cold-start handling
- [x] Dashboard and analytics
- [x] Automated backend tests (57) and CI
- [x] Waste entry UI
- [x] Nightly generation job
- [ ] 4–6 weeks of real data per pilot outlet
- [ ] Two weeks of live plans and an honest MAE report to the owner
