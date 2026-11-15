import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { isSupabaseConfigured, supabase } from "../lib/supabase";
import { longDate, todayISO } from "../lib/format";

const NAV = [
  { to: "/", label: "Dashboard", icon: "grid" },
  { to: "/planner", label: "Prep plan", icon: "spark" },
  { to: "/sales", label: "Sales", icon: "upload" },
  { to: "/analytics", label: "Analytics", icon: "chart" },
] as const;

function Icon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  switch (name) {
    case "grid":
      return (
        <svg viewBox="0 0 24 24" className={className} {...common}>
          <rect x="3.5" y="3.5" width="7" height="7" rx="1.6" />
          <rect x="13.5" y="3.5" width="7" height="7" rx="1.6" />
          <rect x="3.5" y="13.5" width="7" height="7" rx="1.6" />
          <rect x="13.5" y="13.5" width="7" height="7" rx="1.6" />
        </svg>
      );
    case "spark":
      return (
        <svg viewBox="0 0 24 24" className={className} {...common}>
          <path d="M12 3.5l1.9 4.8 4.8 1.9-4.8 1.9L12 16.9l-1.9-4.8L5.3 10.2l4.8-1.9L12 3.5z" />
          <path d="M18.5 15.5l.9 2.2 2.2.9-2.2.9-.9 2.2-.9-2.2-2.2-.9 2.2-.9.9-2.2z" />
        </svg>
      );
    case "upload":
      return (
        <svg viewBox="0 0 24 24" className={className} {...common}>
          <path d="M12 15.5V4.5" />
          <path d="M7.5 9L12 4.5 16.5 9" />
          <path d="M4.5 15.5v2.8a2.2 2.2 0 002.2 2.2h10.6a2.2 2.2 0 002.2-2.2v-2.8" />
        </svg>
      );
    case "chart":
      return (
        <svg viewBox="0 0 24 24" className={className} {...common}>
          <path d="M4 20h16" />
          <rect x="5.5" y="11" width="3.2" height="6" rx="1" />
          <rect x="10.4" y="6.5" width="3.2" height="10.5" rx="1" />
          <rect x="15.3" y="9" width="3.2" height="8" rx="1" />
        </svg>
      );
    default:
      return null;
  }
}

export default function Layout() {
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: api.me });
  const signOut = () => {
    void supabase?.auth.signOut();
  };

  return (
    <div className="min-h-dvh md:flex">
      <aside className="hidden md:flex md:w-64 md:flex-col md:border-r md:border-stone-200 md:bg-white">
        <div className="px-6 pt-7 pb-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-700 text-sm font-bold text-white">
              FW
            </span>
            <div>
              <p className="text-sm font-semibold tracking-tight text-stone-900">FoodWasteOS</p>
              <p className="text-[11px] text-stone-500">Preparation intelligence</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                  isActive
                    ? "bg-emerald-50 text-emerald-900"
                    : "text-stone-600 hover:bg-stone-50 hover:text-stone-900"
                }`
              }
            >
              <Icon name={item.icon} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-stone-100 p-4">
          <p className="truncate text-sm font-medium text-stone-800">
            {me?.restaurant.name ?? "Your restaurant"}
          </p>
          <p className="truncate text-xs text-stone-500">
            {me?.restaurant.location ?? "Set up your kitchen"}
          </p>
          {isSupabaseConfigured && (
            <button
              type="button"
              onClick={signOut}
              className="mt-3 text-xs font-medium text-stone-500 underline underline-offset-2 hover:text-stone-900"
            >
              Sign out
            </button>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-stone-200/80 bg-canvas/90 backdrop-blur md:hidden">
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-700 text-xs font-bold text-white">
                FW
              </span>
              <div>
                <p className="text-sm font-semibold leading-tight">FoodWasteOS</p>
                <p className="text-[11px] leading-tight text-stone-500">
                  {me?.restaurant.name ?? "Your kitchen"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-stone-500">{longDate(todayISO())}</span>
              {isSupabaseConfigured && (
                <button
                  type="button"
                  onClick={signOut}
                  className="-my-2 px-1 py-2 text-xs font-medium text-emerald-800 underline underline-offset-2"
                >
                  Sign out
                </button>
              )}
            </div>
          </div>
          {!isSupabaseConfigured && (
            <p className="bg-amber-100 px-4 py-1.5 text-center text-[11px] font-medium text-amber-900">
              Demo mode · local sample data, not a real account
            </p>
          )}
        </header>

        {!isSupabaseConfigured && (
          <p className="hidden bg-amber-100 px-6 py-2 text-xs font-medium text-amber-900 md:block">
            Demo mode · running against local sample data, not a real account
          </p>
        )}

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 pt-6 md:px-8 md:pb-12 md:pt-8">
          <Outlet />
        </main>

        <nav className="fixed bottom-0 left-0 right-0 z-20 border-t border-stone-200 bg-white/95 backdrop-blur md:hidden">
          <div className="grid grid-cols-4">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium ${
                    isActive ? "text-emerald-800" : "text-stone-500"
                  }`
                }
              >
                <Icon name={item.icon} className="h-5 w-5" />
                {item.label === "Prep plan" ? "Plan" : item.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </div>
    </div>
  );
}
