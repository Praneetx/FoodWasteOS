# FoodWasteOS — Implementation Plan

Current state, remaining work, and acceptance criteria. This plan is grounded in the code, not the
original roadmap: every "done" item below was verified against the repository on 2026-11-16.
Phase 1 is complete; Phase 2 (pilot instrumentation) is next.

---

## 1. Status snapshot

| Area | State | Evidence / notes |
|---|---|---|
| App factory, CORS, health, lifespan | Done | [backend/app/main.py](../../backend/app/main.py) |
| Settings from env | Done | `core/config.py`; dev auth blocked in staging/prod |
| Supabase JWT verification (JWKS + legacy HS256) | Done | `core/security.py` |
| Tenant scope + role checks | Done | `api/deps.py`, `require_role` on mutations |
| Demo tenant + seed | Done | 8 dishes, 77 days, matching waste |
| Dish catalogue | Done | List/create/patch API; UI list + create |
| Sales entry (manual upsert) | Done | `POST /sales`, Sales screen |
| CSV import + template | Done | Flexible headers, partial success, auto-create dishes |
| Waste recording | Done | `GET/POST /waste` + Sales screen form and recent list |
| Weekday baseline + confidence + bands | Done | `ml/baseline.py` |
| Materialised plan + insights + stale | Done | `services/forecasting.py` |
| Planner UI | Done | Prediction, prep, confidence, range, collecting, failure and stale states |
| Dashboard | Done | 4 cards, 14-day chart, tomorrow card |
| Analytics summary | Done | Waste trend, cost, top wasted |
| Accuracy evaluation | Done | `GET /forecasts/accuracy`, Analytics panel |
| RF challenger + features | Experimental | `ml/rf.py`, `ml/features.py`, tests only |
| Walk-forward backtesting | Done | `ml/evaluate.py` |
| Model artifacts registry | **Unwired** | `ml/registry.py` has no callers |
| `model_runs` audit trail | Done | One row per plan generation (`services/model_runs.py`) |
| Nightly plan generation | Done | `POST /cron/generate` + GitHub Actions schedule |
| Waste-rate formula | Decided | `waste / (sales + waste)` for dashboard and analytics (P1.4) |
| RLS enforcement | Deferred | Commented policy only |
| Frontend auth (login, 401, sign-out) | Done | Login page, session-expired notice, sign-out control |
| Backend tests | 57 passing | 10 API + 13 auth/tenancy + 9 cron + 14 data integrity + 5 ML + 6 model runs |
| CI | Configured | `.github/workflows/ci.yml` runs pytest, typecheck and build |
| Frontend typecheck | Passes | `npm run typecheck` |
| Frontend build | Passes | 901.3 kB JS (249.5 kB gzip); Vite warns >500 kB |

---

## 2. Milestones

| Milestone | Outcome | State |
|---|---|---|
| M0 — Foundation | Auth, schema, seed, skeleton, tests | Done |
| M1 — Data in | CSV import, manual entry, catalogue, dashboard | Done |
| M2 — Core value | Baseline forecast, materialised plan, planner UI | Done |
| M3 — Measurement | Analytics, accuracy, backtest harness | Done |
| M4 — Pilot readiness | Waste UI, nightly job, audit trail, metric decision | Done |
| M5 — Pilot | 4–6 weeks real data, 2 weeks live plans, honest MAE review | Not started |
| M6 — Post-pilot | RF promotion decision, notifications, billing | Not started |

---

## 3. Phase 1 — Pilot readiness (complete)

All six items are implemented and verified as of 2026-11-16. The acceptance criteria below remain the
regression contract for future changes.

| Item | State |
|---|---|
| P1.1 Waste entry UI | Done |
| P1.2 Nightly generation | Done |
| P1.3 Persist model runs | Done |
| P1.4 Waste-rate formula | Done — `waste / (sales + waste)` |
| P1.5 Plan reliability polish | Done |
| P1.6 Test the untested paths + CI | Done — 57 tests, CI gate added |

Goal: an outlet can run the product for a week without a spreadsheet workaround or manual refresh.

### P1.1 Waste entry UI — size M — Done

Why: waste drives the entire value story, but before this item the only way to record it was an API
call. Demo data shows waste; real pilots would show none.

- Add a waste form to the Sales screen (dish, date, quantity, reason, notes) or a small dedicated
  section/tab.
- List recent waste rows next to recent sales.
- Invalidate `dashboard`, `analytics`, `plan` after saving.
- Enforce positive quantity and the five reason values client-side for fast feedback.

**Acceptance:** a staff user can record 3 unsold units and see the dashboard waste card and analytics
top-wasted list update without a page reload; re-saving the same dish/date/reason updates instead of
duplicating.

### P1.2 Nightly generation — size S — Done

Why: the plan should exist at 9 AM without the owner opening the app.

- Add a platform cron (GitHub Actions) calling `POST /api/v1/cron/generate` for the next 1–7 days.
- Implement service auth using the existing `CRON_SECRET` (constant-time compare); never reuse a
  human JWT.
- Log one line per run; fail the workflow when any tenant reports an error.

**Acceptance:** with no manual interaction, tomorrow's plan is materialised before 06:00 local time
for all active dishes; a bad secret returns 401/403; no duplicate rows are created.

### P1.3 Persist model runs — size S — Done

Why: confidence and method are already stored per forecast, but training history is not auditable.

- Insert a `model_runs` row whenever plans are generated (or on a weekly cadence): model type,
  window, MAE/WAPE/bias from available accuracy data, params, artifact path (null if none).
- Surface the latest run restaurant-side only if it adds value; otherwise keep it internal.
- Align ORM `JSON` vs DDL `jsonb`.

**Acceptance:** after two generations, `model_runs` contains two rows with correct tenant, model
type and window; no writes outside a transaction.

### P1.4 Decide waste-rate formula — size S (decision) + M (implementation) — Done

Why: the code used `waste / (sales + waste)`; the earlier spec said `waste / prepared` when known.
For the pilot's headline metric, this must be one number everyone trusts.

**Decision (2026-11-16): keep `waste / (sales + waste)`** — waste as a share of food that left the
kitchen (sold or wasted). `prepared_quantity` is optional, so a prepared-based rate would be missing
for a large share of real entries and would make periods incomparable.

Implemented:

- One helper, `services/analytics.waste_rate`, used by both dashboard and analytics.
- Frontend hints corrected to "of food sold or wasted".
- A test pins `10 / (90 + 10) = 0.1` even when `prepared_quantity = 200` is present.
- Architecture, data-model and PRD wording updated; prepared-based rate is out of scope for the pilot.

**Acceptance:** dashboard and analytics use the same formula; tests pin it; UI copy matches.

### P1.5 Plan reliability polish — size S — Done

- Add an explicit "generation failed" state in the planner instead of a generic error notice.
- Show `generated_at` with time, not just date.
- Make the stale threshold configurable or at least named.
- Add a logout control and a "session expired" message on 401.

**Acceptance:** an expired token returns the user to login with a clear message; a stale plan is
visually obvious without reading the small print.

### P1.6 Test the untested paths — size M — Done

Add backend tests for:

- 401/403 paths: missing token, invalid token, unprovisioned user, staff role on owner-only routes.
- Tenant isolation: dish from tenant B is 404 for tenant A.
- CSV dedupe within a file (last wins) and oversized file (413).
- Waste upsert same reason vs different reasons.
- Accuracy metrics with a known small fixture; empty window returns zeros with `evaluated_items=0`.
- `force=false` does not recompute; `force=true` updates `generated_at`.
- Plan deletion for deactivated dishes on force.

**Acceptance:** suite grows from 13 to ≥22 tests, all passing in CI.
**Result:** 57 tests across 6 suites; `.github/workflows/ci.yml` runs pytest and the frontend
typecheck/build on every push and pull request.

---

## 4. Phase 2 — Pilot instrumentation (2 weeks, not started)

| Task | Size | Acceptance |
|---|---|---|
| Structured request logs with tenant, route, status, duration | M | Logs are parseable; tenant is never logged with PII |
| Request ID middleware | S | One ID correlates client error and server log |
| Error tracking (Sentry or platform equivalent) | S | Unhandled exceptions produce an alert with stack trace |
| Import report persistence (log or table) | S | Can answer "why did last week's upload skip rows?" |
| Onboarding checklist in UI | S | New tenant sees import → dishes → plan → accuracy steps |
| Plan print/export (CSV or PDF) | S | Kitchen can print tomorrow's quantities |
| Accuracy trend endpoint (daily series, not just window) | M | Analytics can chart accuracy over time |
| Rate limiting at the edge | S | Import/generate endpoints are bounded |

---

## 5. Phase 3 — Pilot (4–6 weeks)

| Week | Focus | Exit criterion |
|---|---|---|
| 1 | Onboard outlet, backfill 30–90 days | First plan generated from real data |
| 2 | Daily entry habit, fix friction | ≥5 entry days per week, import errors understood |
| 3 | Compare plan vs prep | Waste and stockout counts tracked per week |
| 4 | Review accuracy with owner | MAE/WAPE explained in business terms |
| 5–6 | Decide continuation | Waste down **and** stockouts not up |

Instrumentation to collect: weekly waste quantity, waste cost, stockout days, MAE, WAPE, bias, number
of low-confidence dishes, regeneration frequency.

**Pilot gate:** if waste does not fall, or stockouts rise, stop and diagnose before expanding.

---

## 6. Phase 4 — Post-pilot (prioritised backlog)

| Priority | Item | Notes |
|---|---|---|
| P0 | Stockout-aware demand correction | Use `stockout` flags to impute lower-bound demand; needs enough flags |
| P1 | RF promotion per tenant | Only after ≥5% WAPE win on ≥2 walk-forward windows; store decision in `model_runs` |
| P1 | Morning digest (email/WhatsApp) | Same insights as planner; no new computation |
| P1 | Festival / local event flags | Add per-day event feature once the core signal is proven |
| P2 | Billing / subscription | Stripe/Razorpay; tenant plan limits |
| P2 | POS / aggregator import adapters | Ingestion service + per-source adapters + idempotency keys |
| P2 | Multi-outlet | `outlets` table between restaurants and items |
| P3 | Weather signal | Only if residual analysis shows value |
| P3 | Alembic migrations | At the first pilot schema change |
| P3 | RLS policies | If direct client DB access is ever enabled |

---

## 7. Technical debt ledger

| Item | Impact | Suggested fix |
|---|---|---|
| Unused `ml/registry.py`, `ML_ARTIFACT_DIR` | Dead code, misleading config | Wire into `model_runs` or delete |
| `prepared_quantity` not used in metrics | Intentional after P1.4; field still matters for stockouts and future analysis | Keep stored; document the decision (done) |
| `sample_size` counts total history, not same-weekday count | Confidence semantics slightly opaque | Document or rename `observations_used` |
| `GET /forecasts/plan` writes | Surprising side effect; unsafe behind caches | Keep but document, or add `?generate=false` |
| Forecast `method` and `model_version` duplicate values | Ambiguous intent | Give them distinct meanings or drop one |
| No Alembic | Manual schema drift | Introduce at first change |
| No frontend tests / lint | CI runs typecheck/build, but UI regressions still need manual checks | Add Playwright smoke for 4 screens |
| 901 kB JS bundle | Slow first load on mobile data | Manual chunks (recharts/supabase) or lazy-load Analytics |
| Dataset/demo dates relative to today | Seed output changes daily | Freeze seed dates for screenshot tests if needed |

---

## 8. Test plan

### Current (57)

| Suite | Tests | Covers |
|---|---|---|
| `test_api.py` (10) | API contract | health, demo identity, sale upsert idempotency, partial CSV import, plan generation + stability, stale threshold, cold start, waste + analytics cost, dashboard tomorrow, waste-rate formula parity |
| `test_auth_and_tenancy.py` (13) | Auth and isolation | 401/403 paths, role matrix, cross-tenant 404s |
| `test_cron.py` (9) | Scheduled generation | missing/wrong secret, no user token, generation report, idempotency |
| `test_data_integrity.py` (14) | Data quality | CSV dedupe last-wins, 413 limit, waste upsert by reason, deactivated dishes, force semantics |
| `test_ml.py` (5) | Forecast engine | bands/confidence, recommendation rounding, no-leakage features, walk-forward metrics, RF fit/predict |
| `test_model_runs.py` (6) | Audit trail | one row per generation, accuracy metrics, no run without forecasts |

### Remaining test work

- Frontend Playwright smoke: login → dashboard → planner → sales → analytics
- Accuracy trend series endpoint once Phase 2 adds it

### Verification status (2026-11-16)

- `pytest` — **57 passed** (Python 3.12 via `uv`).
- `npm run typecheck` — passes.
- `npm run build` — passes (901.3 kB, with the >500 kB chunk warning).
- CI workflow added at `.github/workflows/ci.yml`; it runs all three gates on push and PR.
- No live browser run was performed.

---

## 9. Risks to the plan

| Risk | Mitigation |
|---|---|
| Staff don't enter data daily | Keep entry under a minute; import fallback; show value early |
| Waste UI adds friction | One form, sensible defaults, recent rows visible |
| Metric definition changes confuse the pilot | Decide before onboarding; keep UI copy explicit |
| Nightly job fails silently | Health alert on missing run; stale flag in UI |
| RF work distracts from product value | Keep it experimental until baseline is validated |
| Frontend bundle slow on mobile | Code-split analytics/recharts before pilot |

---

## 10. Definition of done

For any feature:

- [ ] Contract in `schemas/` and mirrored in `frontend/src/types.ts`
- [ ] Tenant scope and role check where applicable
- [ ] No fabricated values: nulls render as `—` with an explanation
- [ ] Loading, error and empty states implemented
- [ ] Backend tests for happy path + one boundary
- [ ] `npm run typecheck` and `npm run build` pass
- [ ] Relevant docs in `docs/` updated
- [ ] No new dependency without justification
