# FoodWasteOS API contract (v1)

Base URL: `/api/v1` · Auth: `Authorization: Bearer <supabase-jwt>` (scheduled jobs use
`X-Cron-Secret`) · JSON only (except CSV upload)

All data is scoped to the caller's restaurant. Dates are `YYYY-MM-DD`; timestamps are ISO-8601 UTC;
quantities are integers (or decimals where the unit is weight).

Errors use FastAPI's shape:

```json
{ "detail": "food item not found" }
```

`401` missing/invalid token · `403` role not allowed · `404` not found in this tenant · `422` validation ·
`503` service not configured (cron secret unset).

---

## Auth & profile

### `GET /health`
No auth. Returns `{ "status": "ok", "database": "ok", "version": "0.1.0" }`.

### `GET /me`
```json
{
  "user": { "id": "uuid", "name": "Ayesha", "email": "owner@example.com", "role": "owner" },
  "restaurant": { "id": "uuid", "name": "Spice Route", "location": "Navi Mumbai",
                  "timezone": "Asia/Kolkata", "currency": "INR" }
}
```

---

## Food items

### `GET /food-items`
Returns active items by default (`?include_inactive=true` to include all).
```json
[{ "id": "uuid", "name": "Chicken Biryani", "preparation_unit": "plate",
   "batch_size": 5, "unit_cost": "120.00", "is_active": true }]
```

### `POST /food-items`
```json
{ "name": "Chicken Biryani", "preparation_unit": "plate", "batch_size": 5, "unit_cost": 120 }
```
`201` with the created item. `409` if the name exists for this restaurant.

### `PATCH /food-items/{id}`
Partial update of `name`, `preparation_unit`, `batch_size`, `unit_cost`, `is_active`.
Soft delete: `PATCH` with `{ "is_active": false }` (history and forecasts are preserved).

---

## Sales

### `GET /sales?start=2026-10-01&end=2026-10-31&food_item_id=uuid`
```json
[{ "id": "uuid", "food_item_id": "uuid", "food_item": "Chicken Biryani",
   "sale_date": "2026-10-31", "quantity_sold": 95, "prepared_quantity": 130,
   "promotion": false, "stockout": false }]
```

### `POST /sales`
Upsert on `(food_item_id, sale_date)`.
```json
{ "food_item_id": "uuid", "sale_date": "2026-10-31", "quantity_sold": 95,
  "prepared_quantity": 130, "promotion": false, "stockout": false, "notes": null }
```

### `POST /sales/import`
`multipart/form-data`, field `file` (≤ 5 MB, `.csv`).

Accepted columns (aliases in parentheses):
`date` (sale_date) · `food_item` (item, name) · `quantity_sold` (sold, qty) ·
`prepared_quantity` (prepared, prepared_qty) · `promotion` (promo) · `stockout` · `notes`

```csv
date,food_item,quantity_sold,prepared_quantity,promotion,stockout,notes
2026-10-30,Chicken Biryani,95,130,false,false,
2026-10-30,Paneer Tikka,30,38,true,false,
```

Response — partial success, row-level errors:
```json
{ "imported": 118, "items_created": ["Veg Pulao"], "skipped": 2,
  "errors": [{ "row": 14, "message": "quantity_sold must be a non-negative integer" }] }
```
Rows within a file are deduplicated (last wins) and written with upsert semantics, so re-uploading is safe.

### `GET /sales/template.csv`
Downloads the CSV template.

---

## Waste

### `GET /waste?start=&end=`
```json
[{ "id": "uuid", "food_item_id": "uuid", "food_item": "Paneer Tikka",
   "waste_date": "2026-10-31", "quantity_wasted": "6", "reason": "unsold" }]
```

### `POST /waste`
```json
{ "food_item_id": "uuid", "waste_date": "2026-10-31",
  "quantity_wasted": 6, "reason": "unsold", "notes": null }
```
`reason` ∈ `overproduction | unsold | spoilage | expired | other`.
Upsert on `(food_item_id, waste_date, reason)`.

---

## Forecasts / preparation plan

### `GET /forecasts/plan?target_date=2026-11-16`
Returns the materialized plan. If none exists for the date it is generated on demand.
```json
{
  "target_date": "2026-11-16",
  "model": "weekday_average_v1",
  "generated_at": "2026-11-15T18:30:00Z",
  "stale": false,
  "insights": [
    "Expected demand is 12% above the usual Sunday.",
    "Preparing 450 portions in total; 3 dishes have low confidence."
  ],
  "items": [
    { "food_item_id": "uuid", "food_item": "Chicken Biryani", "preparation_unit": "plate",
      "predicted_demand": 85, "recommended_preparation": 90,
      "lower_bound": 72, "upper_bound": 98,
      "confidence": "medium", "method": "weekday_average_v1", "sample_size": 42,
      "last_same_weekday_sold": 88 }
  ]
}
```
Dishes with < 7 observations are returned with `predicted_demand: null`, a `status` of `collecting_data`
and `observations` count — never a fabricated number.

### `POST /forecasts/generate`
```json
{ "target_date": "2026-11-16", "force": false }
```
Regenerates only if missing unless `force` is true, then returns the same payload as the plan endpoint.
Used by the planner's Generate button. Nightly generation for all tenants uses `/cron/generate`.

### `GET /forecasts/accuracy?days=28`
Compares past forecasts with recorded sales.
```json
{ "window_days": 28, "evaluated_items": 12, "mae": 5.8, "wape": 0.087,
  "bias": -1.2, "within_band_pct": 78.4, "stockout_days": 3 }
```

---

## Scheduled jobs

### `POST /cron/generate`
Header `X-Cron-Secret: <CRON_SECRET>` (no bearer token). Generates upcoming plans for **all**
restaurants. `503` if the server has no `CRON_SECRET` configured, `401` if the header is missing,
`403` if it is wrong.
```json
{ "days_ahead": 1, "force": true }
```
```json
{ "restaurants": 3, "plans_generated": 3, "days_ahead": 1, "force": true, "failed": [] }
```

---

## Analytics

### `GET /analytics/summary?days=30`
```json
{
  "start": "2026-10-17", "end": "2026-11-15",
  "sales_quantity": 12480, "waste_quantity": 940, "waste_rate": 0.070,
  "estimated_waste_cost": 47000, "currency": "INR",
  "top_wasted": [{ "food_item": "Paneer Tikka", "quantity": 210, "cost": 10500 }],
  "weekly_trend": [{ "week_start": "2026-10-19", "sold": 3010, "wasted": 240 }]
}
```
`estimated_waste_cost` is `null` when no unit costs are configured.

### `GET /dashboard?date=2026-11-15`
```json
{
  "date": "2026-11-15",
  "sales_quantity": 420, "waste_quantity": 35, "waste_rate": 0.077,
  "estimated_waste_cost": 1750, "currency": "INR",
  "series": [{ "date": "2026-11-09", "sold": 388, "wasted": 21 }],
  "tomorrow": { "target_date": "2026-11-16", "predicted_total": 430,
                "recommended_total": 452, "vs_usual_pct": 12.0 }
}
```
