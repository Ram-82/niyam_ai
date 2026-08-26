"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";
import {
  BarChart3Icon,
  CalendarCheckIcon,
  ChevronsUpDownIcon,
  FileTextIcon,
  FolderOpenIcon,
  LayoutDashboardIcon,
  SettingsIcon,
  SparklesIcon,
  UsersIcon,
} from "@/components/v2/icons";

type NavItem = {
  href: string;
  label: string;
  icon: ReactNode;
  count?: string;
};

const primaryNav: NavItem[] = [
  { href: "/v2/dashboard", label: "Dashboard", icon: <LayoutDashboardIcon /> },
  { href: "/v2/calendar", label: "Compliance Calendar", icon: <CalendarCheckIcon /> },
  { href: "/v2/clients", label: "Clients", icon: <UsersIcon />, count: "142" },
  { href: "/v2/filings", label: "Filings", icon: <FileTextIcon /> },
  { href: "/v2/contracts", label: "Documents", icon: <FolderOpenIcon /> },
  { href: "/v2/ai-assistant", label: "AI Assistant", icon: <SparklesIcon /> },
  { href: "/v2/reports", label: "Reports", icon: <BarChart3Icon /> },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      style={{
        width: 240,
        flex: "none",
        background: "var(--surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        padding: "16px 12px 12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px 24px" }}>
        <span
          style={{
            width: 20,
            height: 20,
            borderRadius: 6,
            background: "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: 1.5, background: "#fff", transform: "rotate(45deg)" }} />
        </span>
        <span
          style={{
            fontSize: 15,
            lineHeight: "20px",
            fontWeight: "var(--fw-semi)",
            letterSpacing: "var(--tr-nav)",
            color: "var(--text-primary)",
          }}
        >
          Niyam AI
        </span>
      </div>

      <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {primaryNav.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(pathname, item.href)} />
        ))}
      </nav>

      <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
        <button
          type="button"
          className="v2-hover-tint v2-focus"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            width: "100%",
            padding: 8,
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
            font: "inherit",
            color: "var(--text-primary)",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <span
            style={{
              width: 24,
              height: 24,
              flex: "none",
              borderRadius: 6,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 12,
              fontWeight: "var(--fw-semi)",
            }}
          >
            V
          </span>
          <span
            style={{
              flex: 1,
              minWidth: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontSize: 13,
              fontWeight: "var(--fw-medium)",
            }}
          >
            Venkatesh &amp; Co.
          </span>
          <ChevronsUpDownIcon size={16} style={{ color: "var(--text-muted)" }} />
        </button>

        <NavLink
          item={{ href: "/v2/settings", label: "Settings", icon: <SettingsIcon /> }}
          active={isActive(pathname, "/v2/settings")}
        />
      </div>
    </aside>
  );
}

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === "/v2/settings") return pathname.startsWith("/v2/settings");
  return pathname === href || pathname.startsWith(href + "/");
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const style: CSSProperties = active
    ? {
        position: "relative",
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "9px 12px",
        borderRadius: 8,
        background: "var(--accent-soft)",
        color: "var(--accent)",
        fontWeight: "var(--fw-medium)",
        textDecoration: "none",
      }
    : {
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "9px 12px",
        borderRadius: 8,
        color: "var(--text-secondary)",
        textDecoration: "none",
      };

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={active ? "v2-focus" : "v2-nav-link v2-focus"}
      style={style}
    >
      {active && (
        <span
          style={{
            position: "absolute",
            left: -12,
            top: 8,
            bottom: 8,
            width: 3,
            borderRadius: "0 3px 3px 0",
            background: "var(--accent)",
          }}
        />
      )}
      {item.icon}
      <span style={{ flex: 1 }}>{item.label}</span>
      {item.count && (
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{item.count}</span>
      )}
    </Link>
  );
}
