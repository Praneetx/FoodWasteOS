import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import type { Session } from "@supabase/supabase-js";
import { isSupabaseConfigured, supabase } from "./lib/supabase";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import PlannerPage from "./pages/PlannerPage";
import SalesEntryPage from "./pages/SalesEntryPage";
import AnalyticsPage from "./pages/AnalyticsPage";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(isSupabaseConfigured);
  const [sessionExpired, setSessionExpired] = useState(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!supabase) return;
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setChecking(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((event, next) => {
      setSession(next);
      if (event === "SIGNED_IN") setSessionExpired(false);
      // Never keep one user's cached restaurant data after they leave.
      if (event === "SIGNED_OUT") queryClient.clear();
    });

    const handleUnauthorized = () => {
      setSessionExpired(true);
      // Drop the stale token locally too, otherwise a reload would restore it.
      void supabase?.auth.signOut({ scope: "local" });
      setSession(null);
    };
    window.addEventListener("foodwasteos:unauthorized", handleUnauthorized);

    return () => {
      active = false;
      listener.subscription.unsubscribe();
      window.removeEventListener("foodwasteos:unauthorized", handleUnauthorized);
    };
  }, [queryClient]);

  if (checking) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-stone-900">
        <span className="flex h-12 w-12 animate-pulse items-center justify-center rounded-2xl bg-emerald-600 text-sm font-bold text-white">
          FW
        </span>
      </div>
    );
  }

  if (isSupabaseConfigured && !session) {
    return (
      <LoginPage
        notice={
          sessionExpired
            ? "Your session has expired or is no longer valid. Please sign in again."
            : undefined
        }
      />
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="planner" element={<PlannerPage />} />
        <Route path="sales" element={<SalesEntryPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
