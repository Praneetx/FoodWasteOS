import { useState, type FormEvent } from "react";
import { supabase } from "../lib/supabase";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!supabase) return;
    setLoading(true);
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    if (signInError) setError(signInError.message);
    setLoading(false);
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-stone-900 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-600 text-sm font-bold text-white">
            FW
          </span>
          <div>
            <p className="text-lg font-semibold text-white">FoodWasteOS</p>
            <p className="text-xs text-stone-400">Daily preparation intelligence</p>
          </div>
        </div>

        <div className="rounded-3xl bg-white p-7 shadow-2xl">
          <h1 className="text-xl font-semibold tracking-tight">Sign in to your kitchen</h1>
          <p className="mt-1 text-sm text-stone-500">
            Prepare the right amount, every day — without changing how your kitchen works.
          </p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <label className="block">
              <span className="label">Email</span>
              <input
                type="email"
                className="field"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label className="block">
              <span className="label">Password</span>
              <input
                type="password"
                className="field"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>

            {error && (
              <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>
            )}

            <button type="submit" className="btn-primary w-full" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="mt-4 text-center text-xs text-stone-400">
            Accounts are provisioned with your restaurant onboarding.
          </p>
        </div>
      </div>
    </div>
  );
}
