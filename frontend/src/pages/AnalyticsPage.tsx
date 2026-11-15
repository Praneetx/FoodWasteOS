import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";
import { inr, percent, quantity, shortDate } from "../lib/format";
import { ErrorNotice, LoadingBlock, PageHeader } from "../components/Bits";
import { StatCard } from "../components/StatCard";

const RANGES = [7, 30, 90];

function compact(value: number) {
  return value >= 1000 ? `${Math.round(value / 100) / 10}k` : String(value);
}

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);

  const summary = useQuery({
    queryKey: ["analytics", days],
    queryFn: () => api.analytics(days),
  });
  const accuracy = useQuery({
    queryKey: ["accuracy", days],
    queryFn: () => api.accuracy(Math.max(days, 7)),
  });

  if (summary.isLoading) {
    return (
      <div className="space-y-4">
        <LoadingBlock height="h-10" />
        <LoadingBlock height="h-24" />
        <LoadingBlock height="h-72" />
      </div>
    );
  }

  if (summary.error) return <ErrorNotice message={(summary.error as Error).message} />;
  if (!summary.data) return null;

  const data = summary.data;
  const trend = data.weekly_trend.map((row) => ({
    week: shortDate(row.week_start),
    sold: row.sold,
    wasted: row.wasted,
  }));

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Waste trends, savings and how accurate the plans have been"
        action={
          <div className="inline-flex rounded-xl border border-stone-300 bg-white p-1">
            {RANGES.map((range) => (
              <button
                key={range}
                type="button"
                onClick={() => setDays(range)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  days === range ? "bg-stone-900 text-white" : "text-stone-600 hover:bg-stone-100"
                }`}
              >
                {range}d
              </button>
            ))}
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard
          label="Units sold"
          value={quantity(data.sales_quantity)}
          hint={`${shortDate(data.start)} – ${shortDate(data.end)}`}
        />
        <StatCard
          label="Units wasted"
          value={quantity(data.waste_quantity)}
          tone={data.waste_quantity > 0 ? "warn" : "good"}
          hint={`${percent(data.waste_rate)} of prepared food`}
        />
        <StatCard
          label="Estimated waste cost"
          value={inr(data.estimated_waste_cost, data.currency)}
          hint={
            data.estimated_waste_cost === null
              ? "Add unit costs to see savings"
              : "Value of food thrown away"
          }
        />
        <StatCard
          label="Average weekly waste"
          value={quantity(
            trend.length ? data.waste_quantity / Math.max(trend.length, 1) : 0,
          )}
          hint="Units wasted per week in this range"
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="card p-5 lg:col-span-2">
          <div className="mb-4 flex items-baseline justify-between">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">Weekly waste trend</h2>
              <p className="text-xs text-stone-500">Units sold (bars) against wasted (line)</p>
            </div>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={trend} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" vertical={false} />
                <XAxis
                  dataKey="week"
                  tick={{ fontSize: 11, fill: "#78716c" }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 11, fill: "#78716c" }}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                  tickFormatter={compact}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 11, fill: "#b45309" }}
                  tickLine={false}
                  axisLine={false}
                  width={40}
                />
                <Tooltip
                  contentStyle={{ borderRadius: 12, borderColor: "#e7e5e4", fontSize: 12 }}
                />
                <Bar
                  yAxisId="left"
                  dataKey="sold"
                  name="Sold"
                  fill="#047857"
                  radius={[6, 6, 0, 0]}
                  maxBarSize={42}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="wasted"
                  name="Wasted"
                  stroke="#d97706"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-stone-900">Most wasted dishes</h2>
          <p className="text-xs text-stone-500">Where the next plan saves the most</p>
          <ul className="mt-4 space-y-3">
            {data.top_wasted.map((row) => (
              <li key={row.food_item} className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-stone-800">{row.food_item}</p>
                  <p className="text-xs text-stone-500">{quantity(row.quantity)} units</p>
                </div>
                <span className="shrink-0 text-sm tabular-nums text-stone-600">
                  {inr(row.cost, data.currency)}
                </span>
              </li>
            ))}
            {data.top_wasted.length === 0 && (
              <li className="text-sm text-stone-500">No waste recorded in this period.</li>
            )}
          </ul>
        </div>
      </div>

      <div className="card mt-4 p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-stone-900">Forecast accuracy</h2>
            <p className="text-xs text-stone-500">
              Measured against sales recorded after each plan was generated
            </p>
          </div>
          <span className="text-xs text-stone-500">
            {accuracy.data
              ? `${accuracy.data.evaluated_items} dishes · ${accuracy.data.window_days} days`
              : ""}
          </span>
        </div>

        {accuracy.isLoading && <div className="mt-4 h-20 animate-pulse rounded-xl bg-stone-100" />}

        {accuracy.data && accuracy.data.evaluated_items === 0 && (
          <p className="mt-4 rounded-xl bg-stone-50 px-4 py-3 text-sm text-stone-600">
            No archived plans in this window yet. Plans become comparable once tomorrow has
            happened — record sales daily and accuracy appears here.
          </p>
        )}

        {accuracy.data && accuracy.data.evaluated_items > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {[
              { label: "MAE", value: quantity(accuracy.data.mae) },
              { label: "WAPE", value: percent(accuracy.data.wape) },
              { label: "Bias", value: quantity(accuracy.data.bias) },
              { label: "In range", value: `${accuracy.data.within_band_pct.toFixed(0)}%` },
              { label: "Stockout days", value: quantity(accuracy.data.stockout_days) },
              { label: "Dishes scored", value: quantity(accuracy.data.evaluated_items) },
            ].map((metric) => (
              <div key={metric.label}>
                <p className="text-[11px] uppercase tracking-wide text-stone-500">{metric.label}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{metric.value}</p>
              </div>
            ))}
          </div>
        )}

        <p className="mt-4 text-xs leading-relaxed text-stone-400">
          MAE is the average miss in units. WAPE normalises that by total sales, so 8% means the
          plan was off by roughly 8 units for every 100 sold. Bias shows whether the plan tends to
          over- or under-prepare. "In range" is how often actual sales landed inside the predicted
          band.
        </p>
      </div>
    </>
  );
}
