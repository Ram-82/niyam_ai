"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";


const inputCls =
  "mt-1 block w-full border border-rule bg-paper-raised rounded-sm px-2 py-1.5 text-ink " +
  "focus-visible:border-accent";


function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    // Only read the invite token on the client so it never lands in a
    // server-render log. Missing/empty → the page just shows a helpful
    // error rather than posting an empty request.
    const t = params.get("token");
    if (!t) setError("This invite link is missing its token. Ask your admin to resend it.");
    setToken(t);
  }, [params]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("Missing invite token.");
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
      await api("/auth/register", {
        method: "POST",
        body: { invite_token: token, password },
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
          <p className="text-sm text-ink-muted mt-1">
            Account created — one more step.
          </p>
        </div>
        <div
          className="bg-paper-raised border border-rule rounded-md p-6 space-y-3 text-sm text-ink"
          data-testid="register-done"
        >
          <p>
            Your account is set up. Sign in with your new password — you'll be
            walked through TOTP enrolment (Google Authenticator, Authy, 1Password)
            on the way in.
          </p>
          <Link
            href="/login"
            className="inline-block bg-accent text-paper-raised rounded-sm px-4 py-2 font-semibold hover:bg-accent-hover"
            data-testid="register-go-login"
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
        <p className="text-sm text-ink-muted mt-1">
          Accept invite and set your password.
        </p>
      </div>
      <form
        onSubmit={onSubmit}
        className="bg-paper-raised border border-rule rounded-md p-6 space-y-4"
        data-testid="register-form"
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
            data-testid="register-password"
          />
          <span className="mt-1 block text-xs text-ink-muted">
            At least 12 characters. A memorable passphrase works well.
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
            data-testid="register-confirm"
          />
        </label>
        {error && (
          <p
            className="text-sm text-red-fg bg-red-bg border border-rule rounded-sm px-3 py-2"
            data-testid="register-error"
          >
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={loading || !token}
          className="w-full bg-accent text-paper-raised rounded-sm py-2 font-semibold hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50"
          data-testid="register-submit"
        >
          {loading ? "Creating…" : "Create account"}
        </button>
      </form>
    </div>
  );
}


export default function RegisterPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-paper">
      <Suspense fallback={null}>
        <RegisterForm />
      </Suspense>
    </div>
  );
}
