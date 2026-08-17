"use client";

import { Sidebar } from "@/components/v2/shell/Sidebar";
import { TopBar } from "@/components/v2/shell/TopBar";
import { SearchIcon, PlusIcon, XIcon } from "@/components/v2/icons";

/* --- inline SVGs ---------------------------------------------------------- */

const CheckSvg = ({ size = 16, stroke = "currentColor" }: { size?: number; stroke?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke={stroke} strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 13l4 4L19 7" />
  </svg>
);

const SlidersSvg = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 7h9M19 7h1M4 17h5M15 17h5" />
    <circle cx={16} cy={7} r={2.5} />
    <circle cx={12} cy={17} r={2.5} />
  </svg>
);

/* --- data ----------------------------------------------------------------- */

type Ws = {
  init: string; name: string; sub: string;
  role: string;
  avatarBg: string; avatarFg: string;
  roleBg: string; roleFg: string;
  shortcut?: string;
  dashed?: boolean;
  focused?: boolean;
};

const YOURS: Ws[] = [
  {
    init: "GC", name: "Ganesan & Co",
    sub: "Partner · Growth · 84 clients · Chennai, TN",
    role: "Partner",
    avatarBg: "var(--success-soft)", avatarFg: "var(--success)",
    roleBg: "var(--success-soft)", roleFg: "var(--success)",
    shortcut: "⌘1", focused: true,
  },
  {
    init: "MA", name: "Malhotra Advisory LLP",
    sub: "Manager · Enterprise · 218 clients · Mumbai, MH",
    role: "Manager",
    avatarBg: "var(--warning-soft)", avatarFg: "var(--warning)",
    roleBg: "var(--warning-soft)", roleFg: "var(--warning)",
    shortcut: "⌘2",
  },
  {
    init: "RT", name: "Ramesh Textiles Pvt Ltd",
    sub: "External access · 1 client · Bengaluru, KA",
    role: "External",
    avatarBg: "var(--surface)", avatarFg: "var(--text-muted)",
    roleBg: "transparent", roleFg: "var(--text-muted)",
    shortcut: "⌘3", dashed: true,
  },
];

type Invite = {
  init: string; name: string;
  avatarBg: string; avatarFg: string;
  expiry: string; details: string;
};
const INVITES: Invite[] = [
  {
    init: "KA", name: "Kapoor Associates",
    avatarBg: "var(--accent-soft)", avatarFg: "var(--accent)",
    expiry: "Expires in 3d",
    details: "Invited as Partner · Growth plan · Delhi, DL",
  },
  {
    init: "CS", name: "Chandra & Sons",
    avatarBg: "var(--success-soft)", avatarFg: "var(--success)",
    expiry: "Expires in 5d",
    details: "Invited as Manager · Basic plan · Bengaluru, KA",
  },
];

/* --- helpers -------------------------------------------------------------- */

const Kbd = ({ children }: { children: React.ReactNode }) => (
  <span style={{
    height: 20, padding: "0 6px",
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    border: "1px solid var(--border)", borderRadius: 4,
    background: "var(--surface)",
    fontSize: 11, color: "var(--text-muted)",
    fontFamily: "var(--font-mono-v2)",
  }}>{children}</span>
);

const SectionHeader = ({ title, count }: { title: string; count: string }) => (
  <div style={{
    height: 28, padding: "0 16px",
    background: "var(--row-hover)", borderBottom: "1px solid var(--border)",
    display: "flex", alignItems: "center", justifyContent: "space-between",
  }}>
    <span style={{
      fontSize: 11, fontWeight: 500, textTransform: "uppercase",
      letterSpacing: "0.06em", color: "var(--text-muted)",
    }}>{title}</span>
    <span style={{
      fontSize: 11, fontWeight: 500, color: "var(--text-muted)",
    }}>{count}</span>
  </div>
);

const Avatar = ({ init, bg, fg, dashed }: {
  init: string; bg: string; fg: string; dashed?: boolean;
}) => (
  <div style={{
    width: 32, height: 32, flex: "none",
    borderRadius: 8,
    background: bg, color: fg,
    border: dashed ? "1px dashed var(--border-strong)" : "none",
    display: "grid", placeItems: "center",
    fontSize: 12, fontWeight: 600,
  }}>{init}</div>
);

/* --- dashboard body (simplified content behind popover) ------------------ */

function DashboardShell() {
  return (
    <div style={{
      flex: 1, minWidth: 0, background: "var(--bg)",
      display: "flex", flexDirection: "column",
    }}>
      <TopBar />
      <div style={{ flex: 1, padding: 32, display: "flex", flexDirection: "column", gap: 24 }}>
        {/* page header stub */}
        <div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>
            Firm dashboard · Fri, Aug 15
          </div>
          <div style={{
            fontSize: 28, fontWeight: 600, letterSpacing: "-0.01em",
            color: "var(--text-primary)", marginTop: 4,
          }}>
            Good morning, Anand
          </div>
        </div>
        {/* KPI row stubs */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
          {[
            { l: "COMPLIANCE HEALTH", v: "87" },
            { l: "OVERDUE FILINGS", v: "3" },
            { l: "DUE THIS WEEK", v: "12" },
            { l: "ITC MISMATCH", v: "₹2.4L" },
            { l: "REVENUE (MTD)", v: "₹8.6L" },
          ].map(k => (
            <div key={k.l} style={{
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 10, padding: 16, minHeight: 96,
              display: "flex", flexDirection: "column", justifyContent: "space-between",
            }}>
              <div style={{
                fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em",
                color: "var(--text-muted)", fontWeight: 500,
              }}>{k.l}</div>
              <div style={{
                fontSize: 24, fontWeight: 600, color: "var(--text-primary)",
              }}>{k.v}</div>
            </div>
          ))}
        </div>
        {/* two-column body stub */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
          <div style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 10, minHeight: 300, padding: 20,
          }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
              At-risk clients
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              5 clients need attention this week
            </div>
          </div>
          <div style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 10, minHeight: 300, padding: 20,
          }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
              Upcoming deadlines
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* --- workspace row -------------------------------------------------------- */

function WorkspaceRow({ ws, current }: { ws: Ws; current?: boolean }) {
  return (
    <div style={{
      height: 56, padding: "12px 16px",
      borderRadius: 8, position: "relative",
      background: current ? "var(--accent-panel-bg)"
                : ws.focused ? "var(--row-hover)"
                : "transparent",
      boxShadow: ws.focused ? "inset 0 0 0 2px var(--accent)" : "none",
      display: "flex", alignItems: "center", gap: 12,
      cursor: "pointer",
    }}>
      {current && (
        <span style={{
          position: "absolute", left: -8, top: 8, bottom: 8, width: 3,
          borderRadius: "0 3px 3px 0", background: "var(--accent)",
        }} />
      )}
      <Avatar init={ws.init} bg={ws.avatarBg} fg={ws.avatarFg} dashed={ws.dashed} />
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{
          fontSize: 14, lineHeight: "18px", fontWeight: 500,
          color: "var(--text-primary)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>{ws.name}</div>
        <div style={{
          fontSize: 12, lineHeight: "16px", color: "var(--text-muted)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>{ws.sub}</div>
      </div>
      <span style={{
        height: 22, padding: "0 8px", flex: "none",
        display: "inline-flex", alignItems: "center",
        background: current ? "var(--accent)" : ws.roleBg,
        color: current ? "#fff" : ws.roleFg,
        border: ws.dashed ? "1px dashed var(--border-strong)" : "none",
        borderRadius: 6,
        fontSize: 11, fontWeight: 500,
      }}>{ws.role}</span>
      {current ? (
        <span style={{ color: "var(--accent)", flex: "none" }}><CheckSvg size={16} /></span>
      ) : ws.shortcut ? (
        <Kbd>{ws.shortcut}</Kbd>
      ) : null}
    </div>
  );
}

/* --- invite card ---------------------------------------------------------- */

function InviteCard({ inv }: { inv: Invite }) {
  return (
    <div style={{
      minHeight: 72, padding: "12px 16px",
      border: "1px solid var(--border)", borderRadius: 10,
      background: "var(--surface)",
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Avatar init={inv.init} bg={inv.avatarBg} fg={inv.avatarFg} />
        <div style={{
          flex: 1, minWidth: 0,
          fontSize: 14, lineHeight: "18px", fontWeight: 500,
          color: "var(--text-primary)",
        }}>{inv.name}</div>
        <span style={{
          height: 20, padding: "0 8px", flex: "none",
          display: "inline-flex", alignItems: "center",
          background: "var(--warning-soft)", color: "var(--warning)",
          borderRadius: 999, fontSize: 11, fontWeight: 500,
        }}>{inv.expiry}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, height: 28 }}>
        <div style={{
          flex: 1, minWidth: 0,
          fontSize: 12, color: "var(--text-muted)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>{inv.details}</div>
        <button style={{
          height: 28, padding: "0 12px",
          border: "1px solid var(--border)", borderRadius: 8,
          background: "var(--surface)",
          fontSize: 12, fontWeight: 500, color: "var(--text-secondary)",
          cursor: "pointer",
        }}>Decline</button>
        <button style={{
          height: 28, padding: "0 12px", border: "none", borderRadius: 8,
          background: "var(--accent)", color: "#fff",
          fontSize: 12, fontWeight: 500, cursor: "pointer",
        }}>Accept</button>
      </div>
    </div>
  );
}

/* --- popover -------------------------------------------------------------- */

function SwitcherPopover() {
  return (
    <div style={{
      position: "absolute", left: 16, bottom: 128, zIndex: 5,
      width: 360, maxHeight: "calc(100vh - 200px)",
      background: "var(--surface)",
      border: "1px solid var(--border-strong)",
      borderRadius: 12,
      boxShadow: "0 4px 24px rgba(15,23,42,0.12), 0 20px 48px rgba(15,23,42,0.08)",
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      {/* header */}
      <div style={{
        padding: 16, borderBottom: "1px solid var(--border)",
        display: "flex", flexDirection: "column", gap: 12,
      }}>
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{
            fontSize: 11, fontWeight: 500, textTransform: "uppercase",
            letterSpacing: "0.06em", color: "var(--text-muted)",
          }}>Switch workspace</span>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Kbd>⌘⇧O</Kbd>
            <button aria-label="Close"
              style={{
                width: 20, height: 20, border: "none", background: "transparent",
                borderRadius: 4, cursor: "pointer",
                color: "var(--text-muted)", display: "grid", placeItems: "center",
              }}>
              <XIcon size={14} />
            </button>
          </div>
        </div>
        <div style={{
          height: 40, padding: "0 12px",
          border: "1px solid var(--border)", borderRadius: 8,
          background: "var(--surface)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <SearchIcon size={16} />
          <input placeholder="Search workspaces or invitations…"
            style={{
              flex: 1, border: "none", background: "transparent", outline: "none",
              fontSize: 14, color: "var(--text-primary)", minWidth: 0,
            }} />
          <Kbd>/</Kbd>
        </div>
      </div>

      {/* Current */}
      <SectionHeader title="Current" count="1" />
      <div style={{ padding: "8px 8px 0" }}>
        <WorkspaceRow current ws={{
          init: "AC", name: "Acme CA",
          sub: "Owner · Growth · 142 clients · Bengaluru, KA",
          role: "Owner",
          avatarBg: "var(--accent-soft)", avatarFg: "var(--accent)",
          roleBg: "var(--accent)", roleFg: "#fff",
        }} />
      </div>

      {/* Your workspaces */}
      <div style={{ height: 8 }} />
      <SectionHeader title="Your workspaces" count="3" />
      <div style={{ padding: "8px 8px 0", display: "flex", flexDirection: "column", gap: 4 }}>
        {YOURS.map(w => <WorkspaceRow key={w.init} ws={w} />)}
      </div>

      {/* Pending invites */}
      <div style={{ height: 8 }} />
      <SectionHeader title="Pending invites" count="2" />
      <div style={{ padding: "8px 8px 8px", display: "flex", flexDirection: "column", gap: 8 }}>
        {INVITES.map(i => <InviteCard key={i.init} inv={i} />)}
      </div>

      {/* Quick actions */}
      <div style={{
        padding: 8, borderTop: "1px solid var(--border)",
        display: "flex", flexDirection: "column", gap: 4,
      }}>
        <button style={{
          height: 36, padding: "0 12px", border: "none", background: "transparent",
          borderRadius: 8, cursor: "pointer",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <span style={{ color: "var(--accent)" }}><PlusIcon size={16} /></span>
          <span style={{ flex: 1, textAlign: "left",
                        fontSize: 14, color: "var(--text-primary)" }}>
            Create a new workspace
          </span>
          <Kbd>⌘N</Kbd>
        </button>
        <button style={{
          height: 36, padding: "0 12px", border: "none", background: "transparent",
          borderRadius: 8, cursor: "pointer",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <span style={{ color: "var(--text-muted)" }}><SlidersSvg /></span>
          <span style={{ flex: 1, textAlign: "left",
                        fontSize: 14, color: "var(--text-primary)" }}>
            Workspace settings
          </span>
          <Kbd>⌘,</Kbd>
        </button>
      </div>

      {/* footer shortcuts */}
      <div style={{
        height: 36, padding: "0 16px",
        background: "var(--row-hover)",
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Kbd>↑↓</Kbd>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>navigate</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Kbd>↵</Kbd>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>select</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Kbd>⎋</Kbd>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>close</span>
        </div>
        <a href="#" style={{
          marginLeft: "auto",
          fontSize: 11, fontWeight: 500, color: "var(--accent)",
          textDecoration: "none",
        }}>See all shortcuts ↗</a>
      </div>
    </div>
  );
}

/* --- page ---------------------------------------------------------------- */

export default function WorkspaceSwitcherPage() {
  return (
    <div style={{
      minHeight: "100vh", position: "relative",
      display: "flex", alignItems: "stretch",
      background: "var(--bg)",
    }}>
      <Sidebar />
      <DashboardShell />

      {/* dim backdrop */}
      <div style={{
        position: "fixed", inset: 0, zIndex: 4,
        background: "rgba(15,23,42,0.32)",
        backdropFilter: "blur(2px)",
        WebkitBackdropFilter: "blur(2px)",
      }} />

      <SwitcherPopover />
    </div>
  );
}
