"use client";

/* First-time TOTP enrolment.
 *
 * Landed here from sign-in when POST /auth/login returned a
 * totp_setup_token (i.e., user has not confirmed TOTP yet). The setup
 * token is stashed in sessionStorage under "niyam.totp_setup_token".
 *
 * Flow:
 *   1. Read setup token from sessionStorage; if absent, bounce to /v2/sign-in.
 *   2. POST /auth/totp/setup (Bearer: setup_token) → { provisioning_uri, secret }
 *   3. User adds secret to authenticator app; types 6-digit code.
 *   4. POST /auth/totp/verify (Bearer: setup_token) { code } → access + refresh tokens.
 *   5. setAccessToken(access_token), clear sessionStorage, redirect to /v2/dashboard.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { setAccessToken } from "@/lib/auth";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { LoadingState } from "@/components/v2/ui/LoadingState";

/* Inline SVGs — mfa-setup is the only page that needs these three. */

function ShieldCheckIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function CopyIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
      <rect x={9} y={9} width={12} height={12} rx={2} />
      <path d="M5 15V5a2 2 0 0 1 2-2h10" />
    </svg>
  );
}

function CheckIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 13l4 4L19 7" />
    </svg>
  );
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const SETUP_TOKEN_KEY = "niyam.totp_setup_token";

type SetupPayload = {
  provisioning_uri: string;
  secret: string;
};

type VerifyResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

async function fetchSetup(token: string): Promise<SetupPayload> {
  const res = await fetch(`${API_BASE}/auth/totp/setup`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail ?? `Setup failed (${res.status})`);
  }
  return body as SetupPayload;
}

async function verifyCode(token: string, code: string): Promise<VerifyResponse> {
  const res = await fetch(`${API_BASE}/auth/totp/verify`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail ?? `Verification failed (${res.status})`);
  }
  return body as VerifyResponse;
}

export default function MfaSetupPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [payload, setPayload] = useState<SetupPayload | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [code, setCode] = useState("");
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const [copiedField, setCopiedField] = useState<"secret" | "uri" | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);

  // Regenerate the QR whenever the provisioning URI changes. Rendered
  // pure black-on-white so authenticator apps can scan reliably in both
  // light and dark themes (the surrounding tile handles the background).
  useEffect(() => {
    if (!payload?.provisioning_uri) {
      setQrDataUrl(null);
      return;
    }
    let cancelled = false;
    QRCode.toDataURL(payload.provisioning_uri, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 192,
      color: { dark: "#000000", light: "#ffffff" },
    })
      .then((url) => { if (!cancelled) setQrDataUrl(url); })
      .catch(() => { if (!cancelled) setQrDataUrl(null); });
    return () => { cancelled = true; };
  }, [payload?.provisioning_uri]);

  // Bootstrap: read token, call setup.
  useEffect(() => {
    const stored =
      typeof window !== "undefined" ? window.sessionStorage.getItem(SETUP_TOKEN_KEY) : null;
    if (!stored) {
      router.replace("/v2/sign-in");
      return;
    }
    setToken(stored);
    let cancelled = false;
    setLoading(true);
    setSetupError(null);
    fetchSetup(stored)
      .then((r) => { if (!cancelled) setPayload(r); })
      .catch((e) => { if (!cancelled) setSetupError(String(e.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [router]);

  async function onCopy(field: "secret" | "uri", value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(field);
      setTimeout(() => setCopiedField((f) => (f === field ? null : f)), 1500);
    } catch {
      // Clipboard write can fail in insecure contexts — user can still select manually.
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token || code.length !== 6) return;
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await verifyCode(token, code);
      setAccessToken(res.access_token);
      if (typeof window !== "undefined") {
        window.sessionStorage.removeItem(SETUP_TOKEN_KEY);
      }
      router.push("/v2/dashboard");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      // Backend returns "invalid totp" on wrong code.
      setVerifyError(msg === "invalid totp" ? "Wrong code — try again with a freshly generated 6-digit code." : msg);
    } finally {
      setVerifying(false);
    }
  }

  function onBack() {
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(SETUP_TOKEN_KEY);
    }
    router.push("/v2/sign-in");
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 520,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          boxShadow: "0 1px 2px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.06)",
          padding: 32,
          display: "flex",
          flexDirection: "column",
          gap: 24,
        }}
      >
        <header style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <span
            style={{
              width: 40, height: 40, borderRadius: 10,
              background: "var(--accent-soft)", color: "var(--accent)",
              display: "grid", placeItems: "center", flex: "none",
            }}
          >
            <ShieldCheckIcon size={20} />
          </span>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <h1 style={{
              margin: 0, fontSize: 22, lineHeight: "28px", fontWeight: 600,
              letterSpacing: "-0.01em", color: "var(--text-primary)",
            }}>
              Set up two-factor authentication
            </h1>
            <p style={{
              margin: 0, fontSize: 13, lineHeight: "20px", color: "var(--text-secondary)",
            }}>
              Niyam requires TOTP on every sign-in. This one-time setup takes about 60 seconds.
            </p>
          </div>
        </header>

        {loading && <LoadingState message="Preparing your secret…" />}

        {setupError && (
          <ErrorBanner
            message={`Could not start setup: ${setupError}. Sign in again to retry.`}
            onRetry={() => router.push("/v2/sign-in")}
            retryLabel="Back to sign-in"
          />
        )}

        {payload && (
          <>
            <StepCard n={1} title="Install an authenticator app">
              <p style={{ margin: 0, fontSize: 13, lineHeight: "20px", color: "var(--text-secondary)" }}>
                Use Google Authenticator, 1Password, Authy, Bitwarden, or any other TOTP-capable app.
                If you already have one, skip to step 2.
              </p>
            </StepCard>

            <StepCard n={2} title="Add this account">
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{
                  display: "flex", gap: 16, alignItems: "flex-start",
                  padding: 12,
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  background: "var(--surface)",
                }}>
                  <div
                    aria-label="Scan this QR code with your authenticator app"
                    style={{
                      flex: "none",
                      width: 128, height: 128,
                      padding: 6,
                      background: "#ffffff",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                      display: "grid", placeItems: "center",
                    }}
                  >
                    {qrDataUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={qrDataUrl}
                        alt="TOTP QR code"
                        width={116}
                        height={116}
                        style={{ display: "block" }}
                      />
                    ) : (
                      <span style={{ fontSize: 11, color: "#666" }}>QR…</span>
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                    <p style={{
                      margin: 0, fontSize: 13, lineHeight: "18px",
                      fontWeight: "var(--fw-medium)", color: "var(--text-primary)",
                    }}>
                      Scan with your authenticator app
                    </p>
                    <p style={{
                      margin: 0, fontSize: 12, lineHeight: "18px", color: "var(--text-secondary)",
                    }}>
                      Google Authenticator, 1Password, Authy, Bitwarden — all recognise this
                      code. If you can't scan (e.g. desktop app), use the setup key below.
                    </p>
                  </div>
                </div>
                <SecretRow
                  label="Setup key (base32)"
                  value={payload.secret}
                  onCopy={() => onCopy("secret", payload.secret)}
                  copied={copiedField === "secret"}
                />
                <SecretRow
                  label="Or paste this URL into your app"
                  value={payload.provisioning_uri}
                  onCopy={() => onCopy("uri", payload.provisioning_uri)}
                  copied={copiedField === "uri"}
                  truncate
                />
              </div>
            </StepCard>

            <StepCard n={3} title="Enter the 6-digit code your app shows">
              <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  autoFocus
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="000000"
                  disabled={verifying}
                  style={{
                    height: 48, boxSizing: "border-box", padding: "0 14px",
                    border: "1px solid var(--border)", borderRadius: 10,
                    background: "var(--surface)", color: "var(--text-primary)",
                    fontSize: 20, outline: "none",
                    fontFamily: "var(--font-mono-v2)",
                    letterSpacing: "0.4em",
                    textAlign: "center",
                  }}
                />
                {verifyError && <ErrorBanner message={verifyError} />}
                <button
                  type="submit"
                  disabled={verifying || code.length !== 6}
                  style={{
                    height: 44, border: "none", borderRadius: 10,
                    background: "var(--accent)", color: "#fff",
                    fontSize: 14, fontWeight: 500,
                    cursor: verifying || code.length !== 6 ? "not-allowed" : "pointer",
                    opacity: verifying || code.length !== 6 ? 0.6 : 1,
                  }}
                >
                  {verifying ? "Verifying…" : "Verify & finish setup"}
                </button>
              </form>
            </StepCard>
          </>
        )}

        <button
          type="button"
          onClick={onBack}
          style={{
            background: "transparent", border: "none", padding: 0,
            fontSize: 12, fontWeight: 500, color: "var(--text-secondary)",
            cursor: "pointer", textAlign: "left",
          }}
        >
          ← Back to sign-in
        </button>
      </div>
    </div>
  );
}

function StepCard({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section
      style={{
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            width: 24, height: 24, borderRadius: 12,
            background: "var(--accent-soft)", color: "var(--accent)",
            display: "grid", placeItems: "center", flex: "none",
            fontSize: 12, fontWeight: 600,
          }}
        >
          {n}
        </span>
        <h2 style={{
          margin: 0, fontSize: 14, lineHeight: "20px", fontWeight: 600,
          color: "var(--text-primary)",
        }}>
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}

function SecretRow({
  label,
  value,
  onCopy,
  copied,
  truncate,
}: {
  label: string;
  value: string;
  onCopy: () => void;
  copied: boolean;
  truncate?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{
        fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em",
        fontWeight: 500, color: "var(--text-muted)",
      }}>
        {label}
      </span>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "8px 10px",
        border: "1px solid var(--border)",
        borderRadius: 8,
        background: "var(--bg)",
      }}>
        <code style={{
          flex: 1, minWidth: 0,
          fontFamily: "var(--font-mono-v2)",
          fontSize: 13, color: "var(--text-primary)",
          whiteSpace: truncate ? "nowrap" : "normal",
          overflow: truncate ? "hidden" : "visible",
          textOverflow: truncate ? "ellipsis" : "clip",
          wordBreak: truncate ? "normal" : "break-all",
        }}>
          {value}
        </code>
        <button
          type="button"
          onClick={onCopy}
          aria-label={`Copy ${label}`}
          style={{
            flex: "none",
            display: "inline-flex", alignItems: "center", gap: 4,
            padding: "4px 8px",
            border: "1px solid var(--border)",
            borderRadius: 6,
            background: "var(--surface)",
            color: copied ? "var(--success)" : "var(--text-secondary)",
            fontSize: 11, fontWeight: 500, cursor: "pointer",
          }}
        >
          {copied ? <CheckIcon size={12} /> : <CopyIcon size={12} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}
