import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "warn" | "good";
}) {
  const valueTone =
    tone === "warn" ? "text-amber-700" : tone === "good" ? "text-emerald-800" : "text-stone-900";

  return (
    <div className="card p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-stone-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tracking-tight ${valueTone}`}>{value}</p>
      {hint && <p className="mt-1.5 text-xs leading-relaxed text-stone-500">{hint}</p>}
    </div>
  );
}
