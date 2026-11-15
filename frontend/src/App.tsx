import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
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

  useEffect(() => {
    if (!supabase) return;
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setChecking(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
    });

    const handleUnauthorized = () => setSession(null);
    window.addEventListener("foodwasteos:unauthorized", handleUnauthorized);

    return () => {
      active = false;
      listener.subscription.unsubscribe();
      window.removeEventListener("foodwasteos:unauthorized", handleUnauthorized);
    };
  }, []);

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
    return <LoginPage />;
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
