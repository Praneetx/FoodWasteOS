# FoodWasteOS — Frontend Guidelines

Conventions for the React SPA in `frontend/`. Follow these when adding pages, data fetches or
components so the app stays consistent and the API contract stays in one place.

---

## 1. Principles

1. **Four screens, one persona.** Don't add role-specific portals or new top-level navigation without
   a product decision.
2. **Server state belongs to React Query.** Never copy API data into local state for caching.
3. **One API client.** All HTTP goes through [src/lib/api.ts](../../frontend/src/lib/api.ts).
4. **Never fake data.** Show `—`, an empty state, or an explanation. No placeholder zeros for missing
   costs, forecasts or accuracy.
5. **Explainability in the UI.** Confidence, sample size, bands and "what changed" are product
   features, not debug output.
6. **Mobile-first kitchen use.** The plan is read on a phone; desktop is the secondary experience.

---

## 2. Project structure

```
frontend/
├── index.html
├── vite.config.ts            # dev server, /api proxy
├── tailwind.config.js        # canvas/ink colors, Inter, shadow-card
├── src/
│   ├── main.tsx              # QueryClient + BrowserRouter bootstrap
│   ├── App.tsx               # session check, auth gate, routes
│   ├── index.css             # Tailwind layers + component classes
│   ├── types.ts              # API response types (mirror of Pydantic schemas)
│   ├── components/
│   │   ├── Layout.tsx        # sidebar / mobile header / bottom nav / demo banner
│   │   ├── Bits.tsx          # PageHeader, ErrorNotice, LoadingBlock, EmptyState, ConfidenceBadge
│   │   └── StatCard.tsx      # metric card
│   ├── lib/
│   │   ├── api.ts            # request wrapper + endpoint functions + ApiError
│   │   ├── supabase.ts       # client, token access, isSupabaseConfigured
│   │   └── format.ts         # INR, quantities, percentages, dates (en-IN)
│   └── pages/
│       ├── DashboardPage.tsx
│       ├── PlannerPage.tsx
│       ├── SalesEntryPage.tsx
│       ├── AnalyticsPage.tsx
│       └── LoginPage.tsx
```

Rules:

- `pages/` compose screens from `components/` and call `api`.
- `components/` are presentational; they do not fetch (except `Layout`, which fetches `/me` for the
  restaurant name).
- `lib/` contains no JSX.
- Types live in one file so an API change is a single-file diff on the client.

---

## 3. Routing and auth gate

[src/App.tsx](../../frontend/src/App.tsx):

- `checking` starts as `isSupabaseConfigured`; while true, show the pulsing FW mark.
- If Supabase is configured and there is no session → render `LoginPage`.
- If Supabase is not configured → demo mode; render routes directly with a banner from `Layout`.
- Routes are nested under `Layout`; unknown paths redirect to `/`.
- A 401 anywhere dispatches `foodwasteos:unauthorized`; `App` clears the session and shows the login
  screen with a session-expired notice.

Adding a route:

1. Create `src/pages/MyPage.tsx` exporting a default component.
2. Add `<Route path="my-path" element={<MyPage />} />` inside the `Layout` route.
3. Add a nav entry to `NAV` in `Layout.tsx` (icon key + label), keeping the mobile bar at four items.

There is deliberately no client-side role gating beyond what the API enforces; do not hide features
based on role unless the API contract makes that safe.

---

## 4. Data fetching

### Query client defaults

[src/main.tsx](../../frontend/src/main.tsx): `staleTime: 30_000`, `retry: 1`,
`refetchOnWindowFocus: false`.

### Query keys

| Key | Endpoint | Used by |
|---|---|---|
| `["me"]` | `GET /me` | Layout |
| `["items"]` | `GET /food-items` | Sales |
| `["sales"]` | `GET /sales` | Sales |
| `["waste"]` | `GET /waste` | Sales |
| `["dashboard"]` | `GET /dashboard` | Dashboard |
| `["plan", date]` | `GET /forecasts/plan?target_date=` | Planner |
| `["analytics", days]` | `GET /analytics/summary?days=` | Analytics |
| `["accuracy", days]` | `GET /forecasts/accuracy?days=` | Analytics |

Use array keys with parameters; never interpolate parameters into a single string.

### Mutations and invalidation

After a write that changes facts, invalidate the read models that derive from them. The Sales screen
does this centrally:

```ts
queryClient.invalidateQueries({ queryKey: ["sales"] });
queryClient.invalidateQueries({ queryKey: ["waste"] });
queryClient.invalidateQueries({ queryKey: ["items"] });
queryClient.invalidateQueries({ queryKey: ["dashboard"] });
queryClient.invalidateQueries({ queryKey: ["plan"] });
queryClient.invalidateQueries({ queryKey: ["analytics"] });
queryClient.invalidateQueries({ queryKey: ["accuracy"] });
```

Plan regeneration is different: `POST /forecasts/generate` returns the full plan, so write it
straight into the cache with `setQueryData(["plan", date], plan)` and invalidate `["dashboard"]`.
Do not invalidate the plan key immediately after seeding it.

### Loading/error/empty

- **Loading:** `LoadingBlock` skeletons shaped like the final layout (`h-10` header, `h-40`/`h-72`
  blocks). Avoid spinners for page-level loads.
- **Error:** render `<ErrorNotice message={(error as Error).message} />` and stop.
- **Empty:** use `EmptyState` with a concrete next action (e.g. "Add sales data").
- **Partial data:** render what exists. Analytics accuracy is queried independently of the summary
  so one failing endpoint doesn't blank the page.

---

## 5. API client contract

[src/lib/api.ts](../../frontend/src/lib/api.ts):

- Base: `${VITE_API_URL.replace(/\/$/, "")}/api/v1`; empty base → relative `/api/v1` in dev.
- Attaches `Authorization: Bearer <supabase token>` when a session exists.
- Sets `Content-Type: application/json` for non-FormData bodies.
- On 401: dispatches the global event, then throws.
- On non-OK: parses `detail` (string or first validation message) into `ApiError(message, status)`.
- On 204: returns `undefined`.
- Exposes typed functions per endpoint: `me`, `foodItems`, `createFoodItem`, `sales`, `upsertSale`,
  `importCsv`, `waste`, `createWaste`, `dashboard`, `plan`, `generatePlan`, `accuracy`, `analytics`.

When adding an endpoint:

1. Add the response type to `src/types.ts`.
2. Add one function to the `api` object; keep it thin.
3. Never call `fetch` from a page or component.

---

## 6. Auth client and demo mode

[src/lib/supabase.ts](../../frontend/src/lib/supabase.ts):

- `isSupabaseConfigured = Boolean(VITE_SUPABASE_URL && VITE_SUPABASE_ANON_KEY)`.
- `supabase` is `null` in demo mode.
- `getAccessToken()` returns the current session token or `null`.
- Login uses `signInWithPassword` only. There is no sign-up or password-reset screen; a sign-out
  control is available in the sidebar and mobile header.

Demo mode is visible, never silent: `Layout` renders an amber banner on desktop and mobile when
Supabase is not configured. The backend must be `AUTH_MODE=dev` for demo requests to succeed.

---

## 7. Design system

### Tokens

Defined in [tailwind.config.js](../../frontend/tailwind.config.js) and
[src/index.css](../../frontend/src/index.css).

| Token | Value / class | Use |
|---|---|---|
| `canvas` | `#faf9f7` | Page background |
| `ink` | `#1c1917` | Primary text (usually via `stone-900`) |
| `shadow-card` | soft two-layer shadow | `card` surfaces |
| Font | Inter → system sans | Global |
| Radius | `rounded-2xl` cards, `rounded-xl` controls | Consistent softness |
| Primary | `emerald-700` / `emerald-800` hover | Actions, positive metrics, brand mark |
| Neutral | `stone-50…900` | Text, borders, backgrounds |
| Warning | `amber-600/700`, `amber-50` | Waste, medium confidence, demo banner |
| Danger | `rose-700`, `rose-50` | Low confidence, errors, import errors |
| Chart sold | `#047857` | Area/line/bars |
| Chart wasted | `#d97706` | Line |

### Component classes (use these, don't re-invent)

| Class | Definition |
|---|---|
| `.card` | White surface, 1px stone border, `rounded-2xl`, `shadow-card` |
| `.btn` | Base button: inline-flex, rounded-xl, focus ring, disabled opacity |
| `.btn-primary` | Emerald filled action |
| `.btn-ghost` | White with stone border, secondary action |
| `.field` | Form input/select: full width, rounded-xl, emerald focus ring |
| `.label` | Uppercase tracking-wide xs label above fields |
| `.th` / `.td` | Table header/body cell padding and typography |

### Shared components

| Component | Contract |
|---|---|
| `PageHeader` | `title`, optional `subtitle`, optional `action` node |
| `StatCard` | `label`, `value`, optional `hint`, `tone: default \| warn \| good` |
| `ConfidenceBadge` | `high` emerald, `medium` amber, `low` rose, `null` → em dash |
| `ErrorNotice` | Rose panel; pass the human message |
| `LoadingBlock` | Pulse skeleton, configurable height |
| `EmptyState` | Title, body, optional action |

### Layout

- Desktop: fixed-width 16rem sidebar, brand + nav + restaurant footer.
- Mobile: sticky top header, fixed four-tab bottom bar, `pb-24` on main.
- Content: `max-w-6xl` centered, 1rem padding mobile / 2rem desktop.
- Breakpoint: Tailwind `md` (768px) switches layout modes.

### Charts

- Recharts, `ResponsiveContainer`, fixed `h-64` containers.
- Disable animation (`isAnimationActive={false}`) to avoid re-animation on refetch.
- Use the shared chart colors and 11px stone ticks; no axis lines or tick marks.
- Always label series through `name` so tooltips read "Sold"/"Wasted".

---

## 8. Formatting rules

Always use [src/lib/format.ts](../../frontend/src/lib/format.ts), never ad-hoc `toFixed`:

| Function | Output |
|---|---|
| `inr(value, currency = "INR")` | `en-IN` currency, 0 decimals, `—` for null |
| `quantity(value)` | `en-IN` number, max 1 decimal, `—` for null |
| `percent(value)` | `value × 100` with one decimal and `%` |
| `signedPercent(value)` | `+12%` / `-8%` (value already in percent units) |
| `todayISO()` / `tomorrowISO()` | Local-date ISO strings |
| `shortDate(iso)` | `14 Nov` |
| `longDate(iso)` | `Friday, 14 November` |

Nulls are always `—`, never `0`. That rule is a product requirement for confidence and cost.

---

## 9. Forms and validation

- Use controlled inputs with local component state.
- Disable submit while a mutation is pending; change the label (`Saving…`, `Uploading…`).
- Numeric fields: `type="number"`, `min={0}`; step 0.5 for batch size.
- Empty optional numbers are sent as `null`, not `0` (`prepared_quantity`, `unit_cost`).
- Rely on the API for hard validation; surface `ApiError.message` verbatim.
- Clear transient success notices on the next action or via Dismiss.

---

## 10. Accessibility

- Every input has a visible `<label>` (use the `.label` span pattern).
- Buttons have explicit `type` (`button` vs `submit`).
- Use semantic tables with `th` for tabular data; keep header associations.
- Focus states come from `.btn`/`.field` focus rings; do not remove them.
- Color is never the only signal: confidence badges include text, errors include messages.
- Ensure tap targets ≥ 40px on mobile (nav items are 44px).

---

## 11. Do / Don't

| Do | Don't |
|---|---|
| Keep `api.ts` as the only HTTP layer | Call `fetch` in a component |
| Use query keys with parameters | Bake dates into a string key |
| Invalidate derived queries after writes | Leave stale dashboard after saving sales |
| Show `—` for missing cost/forecast | Render `₹0` or `0 units` for unknown values |
| Reuse `.card`, `.btn-*`, `.field` | Invent one-off button styles |
| Keep one primary action per card | Stack multiple emerald CTAs |
| Explain low confidence in copy | Hide uncertainty to look confident |
| Keep charts animation-free | Animate on every refetch |

---

## 12. Adding a page — checklist

- [ ] API function added to `api.ts`; response type added to `types.ts`
- [ ] Query key added to the table above and to the invalidation set if it derives from sales/waste
- [ ] Loading skeleton, error notice, empty state all handled
- [ ] `PageHeader` with title + subtitle; actions passed via `action`
- [ ] Responsive at 375px and 1280px; no horizontal scroll outside tables (tables use `overflow-x-auto`)
- [ ] `npm run typecheck` and `npm run build` pass
- [ ] No new dependency unless justified in the PR description

## 13. Build and quality gates

```bash
cd frontend
npm run typecheck   # tsc --noEmit
npm run build       # vite build -> dist/
```

There is no ESLint or Prettier configuration. Match the existing style: double quotes, trailing
commas, 2-space indentation, function components, explicit return types only where the compiler
needs them.
