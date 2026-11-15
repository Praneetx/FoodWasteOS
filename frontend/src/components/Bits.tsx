import type { ReactNode } from "react";

export function ConfidenceBadge({ level }: { level: "high" | "medium" | "low" | null }) {
  if (!level) return <span className="text-xs text-stone-400">—</span>;
  const styles = {
    high: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    medium: "bg-amber-50 text-amber-800 ring-amber-200",
    low: "bg-rose-50 text-rose-700 ring-rose-200",
  }[level];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ring-1 ring-inset ${styles}`}
    >
      {level}
    </span>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-stone-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-stone-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      {message}
    </div>
  );
}

export function WarningNotice({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-1 leading-relaxed text-amber-900/80">{children}</div>}
    </div>
  );
}

export function LoadingBlock({ height = "h-40" }: { height?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-stone-200/60 ${height}`} />;
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-50">
        <svg
          viewBox="0 0 24 24"
          className="h-5 w-5 text-emerald-700"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4 11h16" />
          <path d="M5.5 11a6.5 6.5 0 0013 0" />
          <path d="M9 4.5c0 1-1 1.5-1 2.5" />
          <path d="M13 4.5c0 1-1 1.5-1 2.5" />
          <path d="M4 19h16" />
        </svg>
      </div>
      <p className="text-base font-semibold text-stone-900">{title}</p>
      <p className="max-w-sm text-sm leading-relaxed text-stone-500">{body}</p>
      {action}
    </div>
  );
}
