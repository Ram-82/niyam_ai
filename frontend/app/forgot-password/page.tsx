"use client";
import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";


const inputCls =
  "mt-1 block w-full border border-rule bg-paper-raised rounded-sm px-2 py-1.5 text-ink " +
  "focus-visible:border-accent";


export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api("/auth/password/forgot", {
        method: "POST",
        body: { email },
        authenticated: false,
      });
      setDone(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        setError(
          "Too many reset requests. Try again later — we cap this to " +
          "protect real inboxes.",
        );
      } else if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError(String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-paper">
      <div className="w-full max-w-sm space-y-4">
        <div>
          <h1 className="font-mono font-semibold text-ink tracking-tight text-lg">
            Niyam AI
          </h1>
          <p className="text-sm text-ink-muted mt-1">Reset your password</p>
        </div>
        {done ? (
          <div
            className="bg-paper-raised border border-rule rounded-md p-6 space-y-3 text-sm text-ink"
            data-testid="forgot-done"
          >
            <p>
              If an account exists for that email, a reset link is on its way.
              The link expires in an hour.
            </p>
            <Link
              href="/login"
              className="inline-block text-accent hover:text-accent-hover hover:underline font-semibold"
            >
              ← Back to sign in
            </Link>
          </div>
        ) : (
          <form
            onSubmit={onSubmit}
            className="bg-paper-raised border border-rule rounded-md p-6 space-y-4"
            data-testid="forgot-form"
          >
            <label className="block">
              <span className="text-sm font-semibold text-ink">Email</span>
              <input
                type="email"
                required
                autoFocus
                className={inputCls}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="forgot-email"
              />
            </label>
            {error && (
              <p
                className="text-sm text-red-fg bg-red-bg border border-rule rounded-sm px-3 py-2"
                data-testid="forgot-error"
              >
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent text-paper-raised rounded-sm py-2 font-semibold hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50"
              data-testid="forgot-submit"
            >
              {loading ? "Sending…" : "Send reset link"}
            </button>
            <div className="text-xs text-ink-muted">
              <Link
                href="/login"
                className="text-accent hover:text-accent-hover hover:underline"
              >
                ← Back to sign in
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
