import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { inr, quantity, shortDate, todayISO } from "../lib/format";
import { ErrorNotice, PageHeader } from "../components/Bits";

const TEMPLATE_URL = `${(import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "")}/api/v1/sales/template.csv`;

export default function SalesEntryPage() {
  const queryClient = useQueryClient();
  const { data: items } = useQuery({ queryKey: ["items"], queryFn: api.foodItems });
  const { data: sales } = useQuery({ queryKey: ["sales"], queryFn: api.sales });

  const [file, setFile] = useState<File | null>(null);
  const [itemId, setItemId] = useState("");
  const [saleDate, setSaleDate] = useState(todayISO());
  const [sold, setSold] = useState("");
  const [prepared, setPrepared] = useState("");
  const [promotion, setPromotion] = useState(false);
  const [stockout, setStockout] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [newDish, setNewDish] = useState({ name: "", batch: "5", cost: "" });

  useEffect(() => {
    if (!itemId && items && items.length > 0) setItemId(items[0].id);
  }, [items, itemId]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["sales"] });
    queryClient.invalidateQueries({ queryKey: ["items"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["plan"] });
    queryClient.invalidateQueries({ queryKey: ["analytics"] });
    queryClient.invalidateQueries({ queryKey: ["accuracy"] });
  };

  const upload = useMutation({
    mutationFn: (selected: File) => api.importCsv(selected),
    onSuccess: (report) => {
      setFile(null);
      setNotice(
        `Imported ${report.imported} row${report.imported === 1 ? "" : "s"}` +
          (report.skipped ? ` · ${report.skipped} skipped` : ""),
      );
      refresh();
    },
  });

  const saveSale = useMutation({
    mutationFn: () =>
      api.upsertSale({
        food_item_id: itemId,
        sale_date: saleDate,
        quantity_sold: Number(sold),
        prepared_quantity: prepared.trim() === "" ? null : Number(prepared),
        promotion,
        stockout,
      }),
    onSuccess: () => {
      setNotice("Today's numbers saved. The plan will use them next.");
      setSold("");
      setPrepared("");
      refresh();
    },
  });

  const createDish = useMutation({
    mutationFn: () =>
      api.createFoodItem({
        name: newDish.name.trim(),
        preparation_unit: "plate",
        batch_size: Number(newDish.batch) || 1,
        unit_cost: newDish.cost.trim() === "" ? null : Number(newDish.cost),
      }),
    onSuccess: () => {
      setNewDish({ name: "", batch: "5", cost: "" });
      refresh();
    },
  });

  const uploadError = upload.error as Error | null;
  const saleError = saveSale.error as Error | null;
  const dishError = createDish.error as Error | null;

  return (
    <>
      <PageHeader
        title="Sales & waste entry"
        subtitle="Feed the forecast — every day of data makes tomorrow's plan sharper"
      />

      {notice && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <span>{notice}</span>
          <button type="button" className="text-xs font-medium underline" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-stone-900">Import sales history</h2>
          <p className="mt-1 text-sm leading-relaxed text-stone-500">
            Upload a CSV with one row per dish per day. Column names are flexible; bad rows are
            reported without rejecting the file.
          </p>

          <div className="mt-4 rounded-xl border border-dashed border-stone-300 bg-stone-50/60 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 py-2 text-xs font-medium text-stone-700 transition hover:bg-stone-100">
                Choose CSV file
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="hidden"
                />
              </label>
              <span className="min-w-0 truncate text-xs text-stone-500">
                {file ? file.name : "No file chosen"}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="btn-primary"
                disabled={!file || upload.isPending}
                onClick={() => file && upload.mutate(file)}
              >
                {upload.isPending ? "Uploading…" : "Upload CSV"}
              </button>
              <a
                href={TEMPLATE_URL}
                className="text-xs font-medium text-emerald-800 underline underline-offset-2"
              >
                Download template
              </a>
            </div>
          </div>

          {uploadError && (
            <div className="mt-4">
              <ErrorNotice message={uploadError.message} />
            </div>
          )}

          {upload.data && (
            <div className="mt-4 rounded-xl bg-stone-50 p-4 text-sm">
              <p className="font-medium text-stone-800">
                {upload.data.imported} rows imported · {upload.data.skipped} skipped
              </p>
              {upload.data.items_created.length > 0 && (
                <p className="mt-1 text-xs text-stone-500">
                  New dishes created: {upload.data.items_created.join(", ")}
                </p>
              )}
              {upload.data.errors.length > 0 && (
                <ul className="mt-2 space-y-1 text-xs text-rose-700">
                  {upload.data.errors.slice(0, 5).map((row) => (
                    <li key={`${row.row}-${row.message}`}>
                      Row {row.row}: {row.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-stone-900">Add today's numbers</h2>
          <p className="mt-1 text-sm leading-relaxed text-stone-500">
            Record what sold and what you prepared. Waste is derived from the difference if you
            leave it out.
          </p>

          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              saveSale.mutate();
            }}
          >
            <label className="block">
              <span className="label">Dish</span>
              <select
                className="field"
                value={itemId}
                onChange={(event) => setItemId(event.target.value)}
                required
              >
                <option value="" disabled>
                  Select a dish
                </option>
                {(items ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="label">Date</span>
                <input
                  type="date"
                  className="field"
                  value={saleDate}
                  onChange={(event) => setSaleDate(event.target.value)}
                  required
                />
              </label>
              <label className="block">
                <span className="label">Sold</span>
                <input
                  type="number"
                  min={0}
                  className="field"
                  placeholder="95"
                  value={sold}
                  onChange={(event) => setSold(event.target.value)}
                  required
                />
              </label>
            </div>

            <label className="block">
              <span className="label">Prepared (optional)</span>
              <input
                type="number"
                min={0}
                className="field"
                placeholder="130"
                value={prepared}
                onChange={(event) => setPrepared(event.target.value)}
              />
            </label>

            <div className="flex flex-wrap gap-5 pt-1 text-sm text-stone-600">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-stone-300 text-emerald-700 focus:ring-emerald-600"
                  checked={promotion}
                  onChange={(event) => setPromotion(event.target.checked)}
                />
                Promotion / offer
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-stone-300 text-emerald-700 focus:ring-emerald-600"
                  checked={stockout}
                  onChange={(event) => setStockout(event.target.checked)}
                />
                Sold out
              </label>
            </div>

            {saleError && <ErrorNotice message={saleError.message} />}

            <button
              type="submit"
              className="btn-primary w-full"
              disabled={saveSale.isPending || !itemId}
            >
              {saveSale.isPending ? "Saving…" : "Save numbers"}
            </button>
          </form>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <div className="card p-5 lg:col-span-2">
          <h2 className="text-sm font-semibold text-stone-900">Dishes</h2>
          <p className="mt-1 text-xs text-stone-500">
            Batch size rounds preparation up (e.g. biryani in batches of 5).
          </p>
          <ul className="mt-3 divide-y divide-stone-100">
            {(items ?? []).map((item) => (
              <li key={item.id} className="flex items-center justify-between py-2.5 text-sm">
                <span className="text-stone-800">{item.name}</span>
                <span className="text-xs text-stone-500">
                  batch {quantity(item.batch_size)} · {inr(item.unit_cost)}
                </span>
              </li>
            ))}
            {(items ?? []).length === 0 && (
              <li className="py-2 text-sm text-stone-500">No dishes yet.</li>
            )}
          </ul>

          <form
            className="mt-4 space-y-2 border-t border-stone-100 pt-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (newDish.name.trim()) createDish.mutate();
            }}
          >
            <input
              className="field"
              placeholder="New dish name"
              value={newDish.name}
              onChange={(event) => setNewDish({ ...newDish, name: event.target.value })}
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                className="field"
                type="number"
                min={0.5}
                step={0.5}
                placeholder="Batch"
                value={newDish.batch}
                onChange={(event) => setNewDish({ ...newDish, batch: event.target.value })}
              />
              <input
                className="field"
                type="number"
                min={0}
                placeholder="Cost / plate"
                value={newDish.cost}
                onChange={(event) => setNewDish({ ...newDish, cost: event.target.value })}
              />
            </div>
            {dishError && <ErrorNotice message={dishError.message} />}
            <button type="submit" className="btn-ghost w-full" disabled={createDish.isPending}>
              {createDish.isPending ? "Adding…" : "Add dish"}
            </button>
          </form>
        </div>

        <div className="card overflow-hidden lg:col-span-3">
          <div className="flex items-center justify-between px-5 py-4">
            <h2 className="text-sm font-semibold text-stone-900">Recent sales</h2>
            <span className="text-xs text-stone-500">Last 30 days</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] border-t border-stone-100">
              <thead className="bg-stone-50/70">
                <tr>
                  <th className="th">Date</th>
                  <th className="th">Dish</th>
                  <th className="th text-right">Sold</th>
                  <th className="th text-right">Prepared</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {(sales ?? []).slice(0, 12).map((sale) => (
                  <tr key={sale.id}>
                    <td className="td whitespace-nowrap text-stone-500">
                      {shortDate(sale.sale_date)}
                    </td>
                    <td className="td">{sale.food_item}</td>
                    <td className="td text-right tabular-nums">{sale.quantity_sold}</td>
                    <td className="td text-right tabular-nums text-stone-500">
                      {sale.prepared_quantity ?? "—"}
                    </td>
                  </tr>
                ))}
                {(sales ?? []).length === 0 && (
                  <tr>
                    <td className="td text-stone-500" colSpan={4}>
                      Nothing recorded yet. Upload a CSV or add today's numbers above.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
