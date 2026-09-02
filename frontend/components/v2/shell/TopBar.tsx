"use client";

import { BellIcon, MoonIcon, SearchIcon, SunIcon } from "@/components/v2/icons";
import { useV2Theme } from "@/components/v2/theme";

export function TopBar() {
  const { theme, toggle } = useV2Theme();

  return (
    <header
      style={{
        height: 64,
        flex: "none",
        boxSizing: "border-box",
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 24,
        padding: "0 32px",
      }}
    >
      <div
        className="v2-search-wrap"
        style={{
          flex: 1,
          maxWidth: 480,
          display: "flex",
          alignItems: "center",
          gap: 8,
          height: 36,
          padding: "0 8px 0 12px",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-input)",
          background: "var(--bg)",
        }}
      >
        <SearchIcon size={16} style={{ color: "var(--text-muted)" }} />
        <input
          type="text"
          placeholder="Search clients, filings, GSTINs, sections…"
          style={{
            flex: 1,
            minWidth: 0,
            border: 0,
            outline: 0,
            background: "transparent",
            font: `400 var(--fs-body)/var(--lh-body) var(--font-sans-v2)`,
            color: "var(--text-primary)",
          }}
        />
        <span
          style={{
            flex: "none",
            padding: "2px 6px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-chip)",
            background: "var(--surface)",
            fontSize: 11,
            fontWeight: "var(--fw-medium)",
            color: "var(--text-muted)",
          }}
        >
          ⌘K
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button
          type="button"
          aria-label="Notifications"
          className="v2-hover-tint v2-focus"
          style={{
            position: "relative",
            width: 36,
            height: 36,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: 0,
            borderRadius: 8,
            background: "transparent",
            color: "var(--text-secondary)",
            cursor: "pointer",
          }}
        >
          <BellIcon />
          <span
            style={{
              position: "absolute",
              top: 5,
              right: 5,
              minWidth: 15,
              height: 15,
              boxSizing: "border-box",
              padding: "0 4px",
              borderRadius: "var(--radius-pill)",
              background: "var(--danger)",
              color: "#fff",
              fontSize: 10,
              lineHeight: "15px",
              fontWeight: "var(--fw-semi)",
              textAlign: "center",
            }}
          >
            3
          </span>
        </button>

        <button
          type="button"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          onClick={toggle}
          className="v2-hover-tint v2-focus"
          style={{
            width: 36,
            height: 36,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: 0,
            borderRadius: 8,
            background: "transparent",
            color: "var(--text-secondary)",
            cursor: "pointer",
          }}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>

        <div style={{ width: 1, height: 24, background: "var(--border)", margin: "0 4px" }} />

        <button
          type="button"
          className="v2-hover-tint v2-focus"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "4px 8px 4px 4px",
            border: 0,
            borderRadius: 8,
            background: "transparent",
            font: "inherit",
            color: "inherit",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <span
            style={{
              width: 32,
              height: 32,
              borderRadius: "var(--radius-pill)",
              background: "var(--accent-soft)",
              color: "var(--accent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 12,
              fontWeight: "var(--fw-semi)",
            }}
          >
            AV
          </span>
          <span style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: 13, lineHeight: "16px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>
              Anand Venkatesh
            </span>
            <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>Partner</span>
          </span>
        </button>
      </div>
    </header>
  );
}
