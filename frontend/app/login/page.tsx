"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import type { LoginResponse } from "@/lib/types";


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
      if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError(String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm bg-white border border-neutral-200 rounded p-6 space-y-4"
        data-testid="login-form"
      >
        <h1 className="text-xl font-semibold">Niyam AI — Sign in</h1>
        <label className="block">
          <span className="text-sm font-medium">Email</span>
          <input
            type="email"
            required
            autoFocus
            className="mt-1 block w-full border border-neutral-300 rounded px-2 py-1"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            data-testid="login-email"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Password</span>
          <input
            type="password"
            required
            className="mt-1 block w-full border border-neutral-300 rounded px-2 py-1"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-testid="login-password"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium">TOTP code (6 digits)</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            className="mt-1 block w-full border border-neutral-300 rounded px-2 py-1 font-mono tracking-widest"
            value={totp}
            onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))}
            data-testid="login-totp"
          />
        </label>
        {error && (
          <p className="text-sm text-red-700" data-testid="login-error">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white rounded py-2 disabled:opacity-50"
          data-testid="login-submit"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
