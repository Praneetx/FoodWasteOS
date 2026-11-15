import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { dateTime, longDate, quantity, todayISO, tomorrowISO } from "../lib/format";
import {
  ConfidenceBadge,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  WarningNotice,
} from "../components/Bits";

export default function PlannerPage() {
  const [date, setDate] = useState(tomorrowISO());
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["plan", date],
    queryFn: () => api.plan(date),
  });

  const regenerate = useMutation({
    mutationFn: () => api.generatePlan(date, true),
    onSuccess: (plan) => {
      queryClient.setQueryData(["plan", date], plan);
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const ready = data?.items.filter((item) => item.status === "ok") ?? [];
  const collecting = data?.items.filter((item) => item.status === "collecting_data") ?? [];
  const totalPredicted = ready.reduce((sum, item) => sum + (item.predicted_demand ?? 0), 0);
  const totalRecommended = ready.reduce(
    (sum, item) => sum + (item.recommended_preparation ?? 0),
    0,
  );
  const lowConfidence = ready.filter((item) => item.confidence === "low").length;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingBlock height="h-10" />
        <LoadingBlock height="h-28" />
        <LoadingBlock height="h-96" />
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Preparation plan"
        subtitle="How much of each dish to prepare, based on your own sales history"
        action={
          <div className="flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="label">Plan for</span>
              <input
                type="date"
                value={date}
                onChange={(event) => setDate(event.target.value)}
                className="field w-40"
              />
            </label>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => regenerate.mutate()}
              disabled={regenerate.isPending}
            >
              {regenerate.isPending ? "Regenerating…" : "Regenerate"}
            </button>
          </div>
        }
      />

      {error && !data && (
        <div className="card p-6" role="alert">
          <p className="text-base font-semibold text-stone-900">
            We couldn't generate this plan
          </p>
          <p className="mt-1 text-sm leading-relaxed text-stone-500">
            Your sales and waste data are safe and nothing was changed. Try again, or pick another
            date. If it keeps failing, the numbers below are not available yet — the plan never
            shows made-up values.
          </p>
          <div className="mt-4">
            <ErrorNotice message={(error as Error).message} />
          </div>
          <button
            type="button"
            className="btn-primary mt-4"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            {isFetching ? "Trying…" : "Try again"}
          </button>
        </div>
      )}

      {regenerate.error && (
        <div className="mb-4">
          <ErrorNotice
            message={`Couldn't refresh the plan: ${(regenerate.error as Error).message}. The previous numbers are still shown.`}
          />
        </div>
      )}

      {data?.stale && (
        <div className="mb-4">
          <WarningNotice title="This plan is out of date">
            It was generated {dateTime(data.generated_at)}, so recent sales are not reflected. Press
            “Refresh numbers” to rebuild it.
          </WarningNotice>
        </div>
      )}

      {data && (
        <>
          <div className="card overflow-hidden">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-stone-100 px-5 py-5">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-widest text-stone-500">
                  {longDate(data.target_date)}
                </p>
                <p className="mt-1 text-sm text-stone-600">
                  Model <span className="font-medium text-stone-800">{data.model}</span> ·{" "}
                  {ready.length} of {data.items.length} dishes forecast
                </p>
              </div>
              <button
                type="button"
                className="btn-primary"
                onClick={() => regenerate.mutate()}
                disabled={regenerate.isPending}
              >
                {regenerate.isPending ? "Working…" : "Refresh numbers"}
              </button>
            </div>

            <div className="grid gap-px bg-stone-100 sm:grid-cols-3">
              <div className="bg-white px-5 py-4">
                <p className="text-xs text-stone-500">Predicted demand</p>
                <p className="mt-1 text-xl font-semibold">{quantity(totalPredicted)}</p>
              </div>
              <div className="bg-white px-5 py-4">
                <p className="text-xs text-stone-500">Recommended preparation</p>
                <p className="mt-1 text-xl font-semibold text-emerald-800">
                  {quantity(totalRecommended)}
                </p>
              </div>
              <div className="bg-white px-5 py-4">
                <p className="text-xs text-stone-500">Low-confidence dishes</p>
                <p className="mt-1 text-xl font-semibold">{lowConfidence}</p>
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-2xl bg-emerald-50/70 p-5 ring-1 ring-inset ring-emerald-100">
            <h2 className="text-sm font-semibold text-emerald-950">What changed</h2>
            <ul className="mt-2 space-y-1.5">
              {data.insights.map((insight) => (
                <li key={insight} className="flex gap-2 text-sm leading-relaxed text-emerald-950/80">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-600" />
                  {insight}
                </li>
              ))}
            </ul>
          </div>

          <div className="card mt-4 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4">
              <h2 className="text-sm font-semibold text-stone-900">Tomorrow's preparation plan</h2>
              <span className="text-xs text-stone-500">
                Generated {dateTime(data.generated_at)}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-t border-stone-100">
                <thead className="bg-stone-50/70">
                  <tr>
                    <th className="th">Dish</th>
                    <th className="th text-right">Predicted</th>
                    <th className="th text-right">Prepare</th>
                    <th className="th">Confidence</th>
                    <th className="th text-right">Last week</th>
                    <th className="th text-right">Typical range</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {data.items.map((item) => (
                    <tr key={item.food_item_id} className="hover:bg-stone-50/50">
                      <td className="td">
                        <p className="font-medium text-stone-900">{item.food_item}</p>
                        <p className="text-xs text-stone-500">
                          {item.status === "ok"
                            ? `Based on ${item.sample_size} days of history`
                            : `Collecting data · ${item.observations ?? 0}/7 days`}
                        </p>
                      </td>
                      <td className="td text-right tabular-nums">
                        {item.predicted_demand === null ? "—" : quantity(item.predicted_demand)}
                      </td>
                      <td className="td text-right">
                        {item.recommended_preparation === null ? (
                          <span className="text-stone-400">—</span>
                        ) : (
                          <span className="inline-flex min-w-14 justify-center rounded-lg bg-emerald-700 px-2.5 py-1 text-sm font-semibold tabular-nums text-white">
                            {quantity(item.recommended_preparation)}
                          </span>
                        )}
                      </td>
                      <td className="td">
                        {item.status === "ok" ? (
                          <ConfidenceBadge level={item.confidence} />
                        ) : (
                          <span className="text-xs text-stone-400">Waiting for history</span>
                        )}
                      </td>
                      <td className="td text-right tabular-nums">
                        {item.last_same_weekday_sold === null
                          ? "—"
                          : quantity(item.last_same_weekday_sold)}
                      </td>
                      <td className="td text-right text-xs tabular-nums text-stone-500">
                        {item.lower_bound === null || item.upper_bound === null
                          ? "—"
                          : `${quantity(item.lower_bound)} – ${quantity(item.upper_bound)}`}
                      </td>
                    </tr>
                  ))}
                  {data.items.length === 0 && (
                    <tr>
                      <td className="td text-stone-500" colSpan={6}>
                        No active dishes yet. Add dishes on the Sales screen.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {collecting.length > 0 && (
            <p className="mt-3 text-xs leading-relaxed text-stone-500">
              {collecting.length} dish{collecting.length > 1 ? "es" : ""} still need at least 7
              days of sales. They are shown as preparing no numbers yet — the plan never invents a
              forecast.
            </p>
          )}

          <p className="mt-4 text-xs leading-relaxed text-stone-400">
            Preparation = predicted demand plus a safety buffer derived from measured variation,
            rounded up to each dish's batch size. Confidence reflects how well this dish's history
            predicts its own demand. Data through {longDate(todayISO())} is included.
          </p>
        </>
      )}
    </>
  );
}
