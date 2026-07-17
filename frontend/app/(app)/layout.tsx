"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { clearAccessToken, getAccessToken } from "@/lib/auth";


export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  if (!ready) return null;

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-neutral-200">
        <div className="max-w-screen-2xl mx-auto flex items-center px-4 h-12">
          <Link href="/command-center" className="font-semibold">
            Niyam AI
          </Link>
          <nav className="ml-8 flex gap-4 text-sm">
            <NavLink href="/command-center" pathname={pathname}>
              Command center
            </NavLink>
            <NavLink href="/imports" pathname={pathname}>
              Imports
            </NavLink>
            <NavLink href="/settings" pathname={pathname}>
              Settings
            </NavLink>
          </nav>
          <button
            onClick={() => {
              clearAccessToken();
              router.push("/login");
            }}
            className="ml-auto text-sm text-neutral-600 hover:underline"
            data-testid="logout"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="max-w-screen-2xl mx-auto p-6">{children}</main>
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
      className={active ? "font-medium text-blue-700" : "text-neutral-700"}
    >
      {children}
    </Link>
  );
}
