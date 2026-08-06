"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { clearAccessToken, getAccessToken } from "@/lib/auth";
import type { Me } from "@/lib/types";


export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  // sandbox_mode comes from the backend (/gsp/mode). The banner CANNOT
  // be removed on the frontend in mock mode — that would risk showing
  // mock 2B data alongside a "live" label. See README §sandbox mode.
  const [sandboxMode, setSandboxMode] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    api<Me>("/auth/me")
      .then(setMe)
      .catch(() => {
        // Token might be revoked/expired — force re-login.
        clearAccessToken();
        router.replace("/login");
      });
    api<{ sandbox_mode: boolean }>("/gsp/mode", { authenticated: false })
      .then((r) => setSandboxMode(!!r.sandbox_mode))
      .catch(() => setSandboxMode(false));
  }, [router]);

  if (!ready) return null;

  return (
    <div className="min-h-screen bg-paper">
      {sandboxMode && (
        <div
          data-testid="sandbox-banner"
          className="bg-amber-100 text-amber-900 border-b border-amber-300 text-xs font-semibold px-6 py-1.5 text-center"
          title="Sandbox mode: no live GSTN data. Every 2B shown here comes from the local mock GSP."
        >
          Sandbox mode — no live GSTN data. All 2B shown here is from the mock GSP.
        </div>
      )}
      <header className="bg-paper-raised border-b border-rule sticky top-0 z-30">
        <div className="max-w-[1320px] mx-auto flex items-center px-6 h-14 gap-8">
          <Link
            href="/command-center"
            className="font-mono font-semibold text-ink tracking-tight text-lg"
            title="Niyam AI"
          >
            Niyam AI
          </Link>
          <nav className="flex gap-6 text-sm h-full items-stretch">
            <NavLink href="/command-center" pathname={pathname}>Command center</NavLink>
            <NavLink href="/imports" pathname={pathname}>Imports</NavLink>
            <NavLink href="/settings" pathname={pathname}>Settings</NavLink>
            <NavLink href="/settings/activity" pathname={pathname}>Activity</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-4 text-xs text-ink-muted">
            {me && (
              <div className="text-right leading-tight">
                <div className="text-ink font-semibold">{me.firm_name || "—"}</div>
                <div className="font-mono">{me.email}</div>
              </div>
            )}
            <button
              onClick={() => { clearAccessToken(); router.push("/login"); }}
              className="text-sm text-ink-muted hover:text-ink border-l border-rule pl-4 h-6 self-center"
              data-testid="logout"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-[1320px] mx-auto px-6 py-8 space-y-8">{children}</main>
    </div>
  );
}


function NavLink({
  href,
  pathname,
  children,
}: {
  href: string;
  pathname: string;
  children: React.ReactNode;
}) {
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <Link
      href={href}
      className={
        "flex items-center border-b-2 -mb-px transition-colors duration-fast " +
        (active
          ? "border-accent text-ink font-semibold"
          : "border-transparent text-ink-muted hover:text-ink")
      }
    >
      {children}
    </Link>
  );
}
