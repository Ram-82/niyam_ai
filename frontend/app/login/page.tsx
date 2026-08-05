"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { RATE_LIMIT_COPY } from "@/lib/constants";
import { formatRetryAt } from "@/lib/format-retry-after";
import type { LoginResponse } from "@/lib/types";


const inputCls =
  "mt-1 block w-full border border-rule bg-paper-raised rounded-sm px-2 py-1.5 text-ink " +
  "focus-visible:border-accent";


export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const body: Record<string, string> = { email, password };
      if (totp) body.totp_code = totp;
      const res = await api<LoginResponse>("/auth/login", {
        method: "POST",
        body,
        authenticated: false,
      });
      if ("access_token" in res) {
        setAccessToken(res.access_token);
        router.push("/command-center");
      } else {
        setError(
          "TOTP not yet enrolled. Enrol via the API before using the dashboard."
        );
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        // 429 account_temporarily_locked: per-email login lockout.
        const at =
          e.retryAfterSeconds != null
            ? formatRetryAt(e.retryAfterSeconds)
            : "a later time";
        setError(RATE_LIMIT_COPY.login_lockout(at));
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
          <p className="text-sm text-ink-muted mt-1">
            GST pre-filing intelligence for CA firms
          </p>
        </div>
        <form
          onSubmit={onSubmit}
          className="bg-paper-raised border border-rule rounded-md p-6 space-y-4"
          data-testid="login-form"
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
              data-testid="login-email"
            />
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-ink">Password</span>
            <input
              type="password"
              required
              className={inputCls}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              data-testid="login-password"
            />
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-ink">TOTP code</span>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              placeholder="6 digits"
              className={inputCls + " font-mono tracking-[0.3em]"}
              value={totp}
              onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))}
              data-testid="login-totp"
            />
          </label>
          {error && (
            <p
              className="text-sm text-red-fg bg-red-bg border border-rule rounded-sm px-3 py-2"
              data-testid="login-error"
            >
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent text-paper-raised rounded-sm py-2 font-semibold hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50"
            data-testid="login-submit"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
