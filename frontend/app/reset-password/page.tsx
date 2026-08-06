"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";


const inputCls =
  "mt-1 block w-full border border-rule bg-paper-raised rounded-sm px-2 py-1.5 text-ink " +
  "focus-visible:border-accent";


function ResetPasswordForm() {
  const params = useSearchParams();
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const t = params.get("token");
    if (!t) {
      setError("This reset link is missing its token. Request a new one from Forgot password.");
    }
    setToken(t);
  }, [params]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("Missing reset token.");
      return;
    }
    if (password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setLoading(true);
    try {
      await api("/auth/password/reset", {
        method: "POST",
        body: { token, new_password: password },
        authenticated: false,
      });
      setDone(true);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError(String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="w-full max-w-sm space-y-4">
        <div>
          <h1 className="font-mono font-semibold text-ink tracking-tight text-lg">
            Niyam AI
          </h1>
          <p className="text-sm text-ink-muted mt-1">Password updated</p>
        </div>
        <div
          className="bg-paper-raised border border-rule rounded-md p-6 space-y-3 text-sm text-ink"
          data-testid="reset-done"
        >
          <p>
            Your password is set. Any other active sessions have been signed
            out — sign in again with the new password.
          </p>
          <Link
            href="/login"
            className="inline-block bg-accent text-paper-raised rounded-sm px-4 py-2 font-semibold hover:bg-accent-hover"
            data-testid="reset-go-login"
          >
            Go to sign-in →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm space-y-4">
      <div>
        <h1 className="font-mono font-semibold text-ink tracking-tight text-lg">
          Niyam AI
        </h1>
        <p className="text-sm text-ink-muted mt-1">Set a new password</p>
      </div>
      <form
        onSubmit={onSubmit}
        className="bg-paper-raised border border-rule rounded-md p-6 space-y-4"
        data-testid="reset-form"
      >
        <label className="block">
          <span className="text-sm font-semibold text-ink">New password</span>
          <input
            type="password"
            required
            autoFocus
            minLength={12}
            className={inputCls}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-testid="reset-password"
          />
          <span className="mt-1 block text-xs text-ink-muted">
            At least 12 characters.
          </span>
        </label>
        <label className="block">
          <span className="text-sm font-semibold text-ink">Confirm password</span>
          <input
            type="password"
            required
            minLength={12}
            className={inputCls}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            data-testid="reset-confirm"
          />
        </label>
        {error && (
          <p
            className="text-sm text-red-fg bg-red-bg border border-rule rounded-sm px-3 py-2"
            data-testid="reset-error"
          >
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={loading || !token}
          className="w-full bg-accent text-paper-raised rounded-sm py-2 font-semibold hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50"
          data-testid="reset-submit"
        >
          {loading ? "Updating…" : "Update password"}
        </button>
      </form>
    </div>
  );
}


export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-paper">
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
