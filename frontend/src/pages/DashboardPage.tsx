import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";
import { inr, percent, quantity, shortDate, signedPercent } from "../lib/format";
import { StatCard } from "../components/StatCard";
import { EmptyState, ErrorNotice, LoadingBlock, PageHeader } from "../components/Bits";

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingBlock height="h-10" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <LoadingBlock />
          <LoadingBlock />
          <LoadingBlock />
          <LoadingBlock />
        </div>
        <LoadingBlock height="h-72" />
      </div>
    );
  }

  if (error) {
    return <ErrorNotice message={(error as Error).message} />;
  }

  if (!data) return null;

  const empty =
    data.series.every((point) => point.sold === 0 && point.wasted === 0) &&
    data.sales_quantity === 0;

  if (empty) {
    return (
      <>
        <PageHeader title="Dashboard" subtitle="Today at a glance" />
        <EmptyState
          title="No sales recorded yet"
          body="Upload a CSV of past sales or add today's numbers. After 7 days per dish, the preparation planner starts predicting tomorrow's demand."
          action={
            <Link to="/sales" className="btn-primary">
              Add sales data
            </Link>
          }
        />
      </>
    );
  }

  const chartData = data.series.map((point) => ({
    day: shortDate(point.date),
    sold: point.sold,
    wasted: point.wasted,
  }));

  const tomorrow = data.tomorrow;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Today at a glance — and what tomorrow needs" />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard
          label="Sold today"
          value={quantity(data.sales_quantity)}
          hint="Plates recorded across all dishes"
        />
        <StatCard
          label="Unsold today"
          value={quantity(data.waste_quantity)}
          tone={data.waste_quantity > 0 ? "warn" : "good"}
          hint={`${percent(data.waste_rate)} of food sold or wasted`}
        />
        <StatCard
          label="Est. waste cost"
          value={inr(data.estimated_waste_cost, data.currency)}
          hint={
            data.estimated_waste_cost === null
              ? "Add dish costs to estimate savings"
              : "Cost of food thrown away today"
          }
        />
        <StatCard
          label="Tomorrow's prep"
          value={tomorrow ? quantity(tomorrow.recommended_total) : "—"}
          tone="good"
          hint={
            tomorrow
              ? `Predicted demand ${quantity(tomorrow.predicted_total)}${
                  tomorrow.vs_usual_pct !== null
                    ? ` · ${signedPercent(tomorrow.vs_usual_pct)} vs usual`
                    : ""
                }`
              : "Open the planner to generate a plan"
          }
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="card p-5 lg:col-span-2">
          <div className="mb-4 flex items-baseline justify-between">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">Last 14 days</h2>
              <p className="text-xs text-stone-500">Units sold against units wasted</p>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-stone-500">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-700" /> Sold
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-amber-600" /> Wasted
              </span>
            </div>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="soldFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#047857" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#047857" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" vertical={false} />
                <XAxis
                  dataKey="day"
                  tick={{ fontSize: 11, fill: "#78716c" }}
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#78716c" }}
                  tickLine={false}
                  axisLine={false}
                  width={46}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 12,
                    borderColor: "#e7e5e4",
                    fontSize: 12,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="sold"
                  name="Sold"
                  stroke="#047857"
                  strokeWidth={2}
                  fill="url(#soldFill)"
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="wasted"
                  name="Wasted"
                  stroke="#d97706"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card flex flex-col justify-between overflow-hidden">
          <div className="bg-stone-900 px-5 py-6 text-white">
            <p className="text-[11px] font-medium uppercase tracking-widest text-stone-400">
              Tomorrow · {tomorrow ? shortDate(tomorrow.target_date) : "—"}
            </p>
            <p className="mt-3 text-4xl font-semibold tracking-tight">
              {tomorrow ? quantity(tomorrow.recommended_total) : "—"}
            </p>
            <p className="mt-1 text-sm text-stone-300">portions recommended</p>
            {tomorrow?.vs_usual_pct !== null && tomorrow?.vs_usual_pct !== undefined && (
              <p className="mt-4 inline-flex rounded-full bg-white/10 px-3 py-1 text-xs text-stone-100">
                {signedPercent(tomorrow.vs_usual_pct)} demand vs a usual day
              </p>
            )}
          </div>
          <div className="space-y-3 p-5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-stone-500">Predicted demand</span>
              <span className="font-medium">
                {tomorrow ? quantity(tomorrow.predicted_total) : "—"}
              </span>
            </div>
            <p className="text-xs leading-relaxed text-stone-500">
              Built from your own weekday history, with a safety buffer sized to how much this
              kitchen's demand usually varies.
            </p>
            <Link to="/planner" className="btn-primary w-full">
              Open preparation plan
            </Link>
          </div>
        </div>
      </div>
    </>
  );
}
