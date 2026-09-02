"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { SunIcon, MoonIcon, ChevronDownIcon, ArrowUpRightIcon } from "@/components/v2/icons";
import { api, ApiError } from "@/lib/api";
import { formatApiError } from "@/lib/format-api-error";
import { setAccessToken } from "@/lib/auth";
import type { LoginResponse } from "@/lib/types";
import { RATE_LIMIT_COPY } from "@/lib/constants";
import { formatRetryAt } from "@/lib/format-retry-after";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";

/* --- inline SVGs specific to this page ------------------------------------ */

const EyeSvg = ({ open }: { open: boolean }) => (
  <svg width={16} height={16} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    {open ? (
      <>
        <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" />
        <circle cx={12} cy={12} r={3} />
      </>
    ) : (
      <>
        <path d="M2 12s3.6-7 10-7c2.5 0 4.6 1 6.3 2.2" />
        <path d="M22 12s-3.6 7-10 7c-2.2 0-4.1-.8-5.6-1.8" />
        <path d="M4 4l16 16" />
      </>
    )}
  </svg>
);

const ShieldCheckSvg = () => (
  <svg width={20} height={20} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

const QuoteSvg = () => (
  <svg width={20} height={20} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 6H5a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h4v2a3 3 0 0 1-3 3" />
    <path d="M20 6h-4a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h4v2a3 3 0 0 1-3 3" />
  </svg>
);

const GoogleG = () => (
  <span style={{
    width: 20, height: 20, borderRadius: 5,
    background: "var(--accent-soft)", color: "var(--accent)",
    display: "grid", placeItems: "center",
    fontSize: 12, fontWeight: 700, letterSpacing: "-0.02em", fontFamily: "Inter, sans-serif",
  }}>G</span>
);

const MsSquare = () => (
  <span style={{
    width: 20, height: 20, borderRadius: 5, overflow: "hidden",
    display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 1,
    background: "var(--border)",
  }}>
    <span style={{ background: "#F25022" }} />
    <span style={{ background: "#7FBA00" }} />
    <span style={{ background: "#00A4EF" }} />
    <span style={{ background: "#FFB900" }} />
  </span>
);

/* --- brand panel content bits --------------------------------------------- */

function DashboardPreview() {
  const cells = [
    { label: "Upcoming deadlines", n: "23", tone: "var(--warning)" },
    { label: "Pending filings",    n: "8",  tone: "var(--warning)" },
    { label: "At-risk clients",    n: "5",  tone: "var(--danger)" },
    { label: "Filed this month",   n: "47", tone: "var(--success)" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, width: 480 }}>
      <div style={{
        boxSizing: "border-box", height: 200, padding: 20,
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, display: "flex", flexDirection: "column", gap: 12,
      }}>
        <div style={{ display: "flex", gap: 8, flex: 1 }}>
          {cells.map(c => (
            <div key={c.label} style={{
              flex: 1, height: 72, padding: 12,
              border: "1px solid var(--border)", borderRadius: 8,
              display: "flex", flexDirection: "column", justifyContent: "space-between",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 4, height: 4, borderRadius: 999, background: c.tone }} />
                <div style={{
                  fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em",
                  color: "var(--text-muted)", fontWeight: 500,
                }}>{c.label}</div>
              </div>
              <div style={{
                fontSize: 20, lineHeight: "24px", fontWeight: 600,
                color: "var(--text-primary)",
              }}>{c.n}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 3, height: 4, marginTop: 4 }}>
          <div style={{ width: "60%", borderRadius: 999, background: "var(--success)" }} />
          <div style={{ width: "25%", borderRadius: 999, background: "var(--warning)" }} />
          <div style={{ width: "15%", borderRadius: 999, background: "var(--danger)" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Firm compliance health · 87/100
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Live preview</div>
        </div>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
        This is what your firm's dashboard will look like.
      </div>
    </div>
  );
}

function Stats() {
  const items = [
    { n: "2,400+",     l: "CA firms" },
    { n: "1.2 M",      l: "Filings filed / year" },
    { n: "₹9,400 Cr",  l: "Compliance value / year" },
  ];
  return (
    <div style={{ width: 480, minHeight: 48, display: "flex", alignItems: "center" }}>
      {items.map((it, i) => (
        <div key={it.l} style={{
          flex: 1, display: "flex", flexDirection: "column", gap: 2,
          paddingLeft: i === 0 ? 0 : 20,
          borderLeft: i === 0 ? "none" : "1px solid var(--border)",
        }}>
          <div style={{
            fontSize: 24, lineHeight: "28px", fontWeight: 600,
            color: "var(--text-primary)", letterSpacing: "-0.01em",
          }}>{it.n}</div>
          <div style={{
            fontSize: 11, lineHeight: "14px", fontWeight: 500,
            textTransform: "uppercase", letterSpacing: "0.06em",
            color: "var(--text-muted)",
          }}>{it.l}</div>
        </div>
      ))}
    </div>
  );
}

function TrustBadges() {
  const badges = [
    { init: "S2", label: "SOC 2 Type II" },
    { init: "IS", label: "ISO 27001" },
    { init: "GS", label: "GSTN GSP-certified" },
    { init: "DP", label: "DPDP Act ready" },
  ];
  return (
    <div style={{ width: 480, display: "flex", gap: 8, flexWrap: "wrap" }}>
      {badges.map(b => (
        <div key={b.label} style={{
          height: 40, boxSizing: "border-box",
          display: "inline-flex", alignItems: "center", gap: 8,
          padding: "0 14px",
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 8, fontSize: 12, color: "var(--text-secondary)",
        }}>
          <span style={{
            width: 20, height: 20, borderRadius: 5,
            background: "var(--row-hover)", color: "var(--text-primary)",
            display: "grid", placeItems: "center",
            fontSize: 9, fontWeight: 600, letterSpacing: "0.02em",
          }}>{b.init}</span>
          <span style={{ fontWeight: 500 }}>{b.label}</span>
        </div>
      ))}
    </div>
  );
}

function Testimonial() {
  return (
    <div style={{
      width: 480, minHeight: 160, boxSizing: "border-box",
      padding: 24, background: "var(--surface)",
      border: "1px solid var(--border)", borderRadius: 12,
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ color: "var(--text-muted)" }}><QuoteSvg /></div>
      <div style={{
        margin: 0, fontSize: 15, lineHeight: "24px",
        color: "var(--text-primary)",
      }}>
        Niyam cut our July filing cycle from nine days to three. It's the first tool my whole team asks for on day one.
      </div>
      <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8,
          background: "var(--accent-soft)", color: "var(--accent)",
          display: "grid", placeItems: "center",
          fontSize: 12, fontWeight: 600,
        }}>MG</div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 14, lineHeight: "18px", fontWeight: 500,
                        color: "var(--text-primary)" }}>Meera Ganesan</div>
          <div style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
            Managing Partner · Ganesan &amp; Co, Chennai
          </div>
        </div>
      </div>
    </div>
  );
}

/* --- brand panel ---------------------------------------------------------- */

function BrandPanel() {
  return (
    <div style={{
      flex: 1, minWidth: 0, position: "relative",
      boxSizing: "border-box", padding: "0 0 0 96px",
      background: "var(--bg)",
      backgroundImage: "radial-gradient(rgba(15,23,42,0.06) 1px, transparent 1px)",
      backgroundSize: "16px 16px",
      borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column", justifyContent: "center", gap: 32,
    }}>
      <div style={{ width: 480, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{
          fontSize: 11, lineHeight: "16px", fontWeight: 500,
          letterSpacing: "0.06em", textTransform: "uppercase",
          color: "var(--accent)",
        }}>
          Compliance intelligence for CA firms
        </div>
        <h2 style={{
          margin: 0, fontSize: 32, lineHeight: "40px", fontWeight: 600,
          letterSpacing: "-0.02em", color: "var(--text-primary)",
        }}>
          The trusted compliance workspace for India's Chartered Accountants.
        </h2>
      </div>
      <DashboardPreview />
      <Stats />
      <TrustBadges />
      <Testimonial />
      <a href="#" style={{
        position: "absolute", right: 32, bottom: 32,
        height: 32, boxSizing: "border-box",
        display: "inline-flex", alignItems: "center", gap: 8,
        padding: "0 12px",
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 8, fontSize: 12, color: "var(--text-secondary)",
        textDecoration: "none",
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: 999, background: "var(--success)",
          flex: "none",
        }} />
        System status · All systems operational
        <ArrowUpRightIcon size={12} />
      </a>
    </div>
  );
}

/* --- top navigation ------------------------------------------------------- */

function Nav({ theme, onToggleTheme }: { theme: "light" | "dark"; onToggleTheme: () => void }) {
  return (
    <>
      <a href="#" style={{
        position: "absolute", top: 32, left: 32, zIndex: 3,
        display: "flex", alignItems: "center", gap: 8,
        textDecoration: "none",
      }}>
        <span style={{
          width: 24, height: 24, borderRadius: 7,
          background: "var(--accent)", display: "grid", placeItems: "center",
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: 2, background: "#fff",
            transform: "rotate(45deg)",
          }} />
        </span>
        <span style={{
          fontSize: 17, lineHeight: "24px", fontWeight: 600,
          letterSpacing: "-0.01em", color: "var(--text-primary)",
        }}>Niyam AI</span>
      </a>
      <div style={{
        position: "absolute", top: 32, right: 32, zIndex: 3,
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <button onClick={onToggleTheme}
          aria-label="Toggle theme"
          style={{
            width: 32, height: 32, border: "none", background: "transparent",
            borderRadius: 8, cursor: "pointer", color: "var(--text-secondary)",
            display: "grid", placeItems: "center",
          }}>
          {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
        </button>
        <button style={{
          height: 32, display: "flex", alignItems: "center", gap: 6,
          padding: "0 10px",
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 8, fontSize: 12, fontWeight: 500,
          color: "var(--text-secondary)", cursor: "pointer",
        }}>
          EN <ChevronDownIcon size={12} />
        </button>
        <a href="#" style={{
          display: "inline-flex", alignItems: "center",
          height: 32, padding: "0 8px", fontSize: 12, fontWeight: 500,
          color: "var(--accent)", textDecoration: "none",
        }}>
          New to Niyam? Book a demo →
        </a>
      </div>
    </>
  );
}

/* --- page ---------------------------------------------------------------- */

type Step = "creds" | "totp" | "setup_required";

export default function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [show, setShow] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [step, setStep] = useState<Step>("creds");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    if (typeof document !== "undefined") {
      const wrap = document.querySelector<HTMLElement>('[data-theme-v="2"]');
      if (wrap) {
        if (next === "dark") wrap.setAttribute("data-theme", "dark");
        else wrap.removeAttribute("data-theme");
      }
    }
  };

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
        router.push("/v2/dashboard");
        return;
      }
      // First-time login: backend returned a totp_setup_token. Stash it so
      // the enrolment page can pick it up, then navigate. sessionStorage
      // clears on tab close — the token has a short TTL anyway.
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem("niyam.totp_setup_token", res.totp_setup_token);
      }
      router.push("/v2/mfa-setup");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        const detail =
          typeof err.body === "object" && err.body !== null && "detail" in err.body
            ? String((err.body as { detail: unknown }).detail)
            : err.message;
        if (detail === "totp_required") {
          setStep("totp");
          setError(null);
          return;
        }
        setError(detail || "Sign-in failed.");
      } else if (err instanceof ApiError && err.status === 401) {
        setError("Wrong email or password.");
      } else if (err instanceof ApiError && err.status === 429) {
        const at =
          err.retryAfterSeconds != null
            ? formatRetryAt(err.retryAfterSeconds)
            : "a later time";
        setError(RATE_LIMIT_COPY.login_lockout(at));
      } else if (err instanceof ApiError) {
        setError(err.message || `Sign-in failed (${err.status}).`);
      } else {
        setError(formatApiError(err));
      }
    } finally {
      setLoading(false);
    }
  }

  function resetToCreds() {
    setStep("creds");
    setTotp("");
    setError(null);
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "stretch",
      overflow: "hidden", background: "var(--surface)", position: "relative",
    }}>
      <Nav theme={theme} onToggleTheme={toggleTheme} />

      {/* left: form panel */}
      <div style={{
        width: 800, flex: "none", display: "flex", alignItems: "center",
        justifyContent: "center", padding: "120px 32px 64px",
      }}>
        <div style={{ width: 440, display: "flex", flexDirection: "column", gap: 32 }}>
          {/* form card */}
          <form onSubmit={onSubmit} style={{
            padding: 32, boxSizing: "border-box",
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 12,
            boxShadow: "0 1px 2px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.06)",
            display: "flex", flexDirection: "column", gap: 24,
          }}>
            <header style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <h1 style={{
                margin: 0, fontSize: 24, lineHeight: "32px", fontWeight: 600,
                letterSpacing: "-0.01em", color: "var(--text-primary)",
              }}>
                Sign in to Niyam
              </h1>
              <p style={{
                margin: 0, fontSize: 14, lineHeight: "20px",
                color: "var(--text-secondary)",
              }}>
                Enter your firm email to continue to your workspace.
              </p>
            </header>

            {/* SSO — not wired; backend has no SSO endpoints yet. */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <button type="button" disabled title="SSO ships with the enterprise release" style={{
                height: 40, display: "flex", alignItems: "center", justifyContent: "center",
                gap: 10, padding: "0 12px",
                border: "1px solid var(--border)", borderRadius: 8,
                background: "var(--surface)", color: "var(--text-primary)",
                fontSize: 14, fontWeight: 400, cursor: "not-allowed", opacity: 0.5,
              }}>
                <GoogleG /> Continue with Google
              </button>
              <button type="button" disabled title="SSO ships with the enterprise release" style={{
                height: 40, display: "flex", alignItems: "center", justifyContent: "center",
                gap: 10, padding: "0 12px",
                border: "1px solid var(--border)", borderRadius: 8,
                background: "var(--surface)", color: "var(--text-primary)",
                fontSize: 14, fontWeight: 400, cursor: "not-allowed", opacity: 0.5,
              }}>
                <MsSquare /> Continue with Microsoft 365
              </button>
              <div style={{
                fontSize: 11, lineHeight: "16px", color: "var(--text-muted)",
              }}>
                SSO is on the enterprise roadmap. For now, sign in with your firm email.
              </div>
            </div>

            {/* divider */}
            <div style={{
              position: "relative", height: 16,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <div style={{
                position: "absolute", left: 0, right: 0, height: 1,
                background: "var(--border)",
              }} />
              <span style={{
                position: "relative", padding: "0 8px",
                background: "var(--surface)",
                fontSize: 11, lineHeight: "16px", fontWeight: 500,
                letterSpacing: "0.08em", textTransform: "uppercase",
                color: "var(--text-muted)",
              }}>Or continue with email</span>
            </div>

            {/* email */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <label htmlFor="email" style={{
                fontSize: 12, lineHeight: "16px", fontWeight: 500,
                letterSpacing: "0.06em", textTransform: "uppercase",
                color: "var(--text-muted)",
              }}>Work email</label>
              <input id="email" type="email" value={email} required
                autoComplete="email" autoFocus
                onChange={e => setEmail(e.target.value)}
                disabled={step !== "creds"}
                placeholder="you@yourfirm.in"
                style={{
                  height: 44, boxSizing: "border-box", padding: "0 14px",
                  border: "1px solid var(--border)", borderRadius: 10,
                  background: "var(--surface)", color: "var(--text-primary)",
                  fontSize: 14, outline: "none",
                  opacity: step !== "creds" ? 0.6 : 1,
                }} />
            </div>

            {/* password */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 16 }}>
                <label htmlFor="password" style={{
                  fontSize: 12, lineHeight: "16px", fontWeight: 500,
                  letterSpacing: "0.06em", textTransform: "uppercase",
                  color: "var(--text-muted)",
                }}>Password</label>
                <a href="/forgot-password" style={{ fontSize: 12, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
                  Forgot password?
                </a>
              </div>
              <div style={{ position: "relative" }}>
                <input id="password" type={show ? "text" : "password"} value={password}
                  required autoComplete="current-password"
                  onChange={e => setPassword(e.target.value)}
                  disabled={step !== "creds"}
                  style={{
                    width: "100%", height: 44, boxSizing: "border-box",
                    padding: "0 44px 0 14px",
                    border: "1px solid var(--border)", borderRadius: 10,
                    background: "var(--surface)", color: "var(--text-primary)",
                    fontSize: 14, outline: "none",
                    opacity: step !== "creds" ? 0.6 : 1,
                  }} />
                <button type="button" onClick={() => setShow(s => !s)}
                  aria-label={show ? "Hide password" : "Show password"}
                  style={{
                    position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                    width: 24, height: 24, border: "none", background: "transparent",
                    borderRadius: 6, color: "var(--text-muted)", cursor: "pointer",
                    display: "grid", placeItems: "center",
                  }}>
                  <EyeSvg open={show} />
                </button>
              </div>
              <div style={{
                fontSize: 12, lineHeight: "16px", color: "var(--text-muted)",
              }}>
                Case-sensitive · min 12 characters
              </div>
            </div>

            {/* TOTP field — revealed once backend requires it */}
            {step === "totp" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 16 }}>
                  <label htmlFor="totp" style={{
                    fontSize: 12, lineHeight: "16px", fontWeight: 500,
                    letterSpacing: "0.06em", textTransform: "uppercase",
                    color: "var(--text-muted)",
                  }}>Authenticator code</label>
                  <button type="button" onClick={resetToCreds} style={{
                    background: "transparent", border: "none", padding: 0,
                    fontSize: 12, fontWeight: 500, color: "var(--accent)", cursor: "pointer",
                  }}>
                    Use different email
                  </button>
                </div>
                <input id="totp" type="text" value={totp}
                  inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoFocus
                  autoComplete="one-time-code"
                  onChange={e => setTotp(e.target.value.replace(/\D/g, ""))}
                  placeholder="000000"
                  style={{
                    height: 44, boxSizing: "border-box", padding: "0 14px",
                    border: "1px solid var(--border)", borderRadius: 10,
                    background: "var(--surface)", color: "var(--text-primary)",
                    fontSize: 18, outline: "none",
                    fontFamily: "var(--font-mono-v2)",
                    letterSpacing: "0.4em",
                    textAlign: "center",
                  }} />
                <div style={{
                  fontSize: 12, lineHeight: "16px", color: "var(--text-muted)",
                }}>
                  6-digit code from your authenticator app (Google Authenticator, 1Password, Authy…).
                </div>
              </div>
            )}

            {/* Error banner */}
            {error && <ErrorBanner message={error} />}

            {/* primary CTA */}
            <button type="submit" disabled={loading || step === "setup_required"}
              title={step === "setup_required" ? "Open the classic /login flow to enrol TOTP, then return here." : undefined}
              style={{
              height: 44, position: "relative",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              border: "none", borderRadius: 10,
              background: "var(--accent)", color: "#fff",
              fontSize: 14, fontWeight: 500,
              cursor: loading || step === "setup_required" ? "not-allowed" : "pointer",
              opacity: loading || step === "setup_required" ? 0.6 : 1,
            }}>
              {loading ? "Signing in…" : step === "totp" ? "Verify & sign in" : "Continue"}
              {!loading && (
                <span style={{
                  position: "absolute", right: 12,
                  padding: "1px 6px", borderRadius: 4,
                  background: "rgba(255,255,255,.18)",
                  fontSize: 11, color: "rgba(255,255,255,.85)",
                  fontFamily: "var(--font-mono-v2)",
                }}>↵</span>
              )}
            </button>

            {/* sign-up prompt */}
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "center",
              gap: 6, fontSize: 12, color: "var(--text-secondary)",
            }}>
              <span>Don&apos;t have an account?</span>
              <a href="#" style={{ fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
                Contact your firm admin →
              </a>
            </div>

            {/* footer */}
            <div style={{
              paddingTop: 16, borderTop: "1px solid var(--border)",
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-muted)" }}>
                <a href="#" style={{ color: "inherit", textDecoration: "none" }}>Terms of use</a>
                <span>·</span>
                <a href="#" style={{ color: "inherit", textDecoration: "none" }}>Privacy</a>
                <span>·</span>
                <a href="#" style={{ color: "inherit", textDecoration: "none" }}>DPA</a>
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                v · 2026.08.13
              </div>
            </div>
          </form>

          {/* MFA banner — TOTP is required for every confirmed account. */}
          <div style={{
            width: 440, minHeight: 64, padding: 16, boxSizing: "border-box",
            background: "var(--accent-panel-bg)",
            border: "1px solid var(--accent-panel-border)",
            borderRadius: 10, display: "flex", alignItems: "center", gap: 12,
          }}>
            <span style={{ color: "var(--accent)", flex: "none" }}><ShieldCheckSvg /></span>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, lineHeight: "18px", fontWeight: 500, color: "var(--text-primary)" }}>
                TOTP is mandatory on every sign-in.
              </div>
              <div style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }}>
                You'll be prompted for your 6-digit authenticator code after email + password.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* right: brand panel */}
      <BrandPanel />
    </div>
  );
}
