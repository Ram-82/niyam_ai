"use client";

import { useState, type CSSProperties } from "react";
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  MoreHorizontalIcon,
  PlusIcon,
  SearchIcon,
} from "@/components/v2/icons";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import {
  buildMemberRows,
  seatsSummary,
  useInviteMutation,
  useSettingsData,
  type FirmSettings,
  type MemberRow,
} from "./useSettingsData";

// Role palette + demo shape. Backend distinguishes only admin/staff;
// UI-only labels ("Owner", "Invited") are derived in useSettingsData.
type RoleName = "Owner" | "Admin" | "Staff" | "Invited" | "Partner" | "Manager" | "Associate" | "External";
type MfaKind = "Yubikey" | "TOTP" | "Not set" | "—";
type StatusKind = "active" | "pending" | "inactive" | "invited";

type Member = {
  name: string;
  initials: string;
  email: string;
  subtitle?: string;
  role: RoleName;
  scopeMain: string;
  scopeMeta: string;
  lastActive: string;
  mfa: MfaKind;
  status: { label: string; kind: StatusKind };
  isOwner?: boolean;
};

const NAV_GROUPS: { label: string; links: { label: string; active?: boolean }[] }[] = [
  { label: "Account", links: [
    { label: "Profile" },
    { label: "Security & sign-in" },
    { label: "Notifications" },
    { label: "Personal API tokens" },
  ] },
  { label: "Firm", links: [
    { label: "Firm details" },
    { label: "Branding" },
    { label: "Filing preferences" },
    { label: "Rule pack overrides" },
  ] },
  { label: "Workspace", links: [
    { label: "Team & permissions", active: true },
    { label: "Plan & billing" },
    { label: "Usage & limits" },
    { label: "Audit log" },
  ] },
  { label: "Integrations", links: [
    { label: "GSP connection" },
    { label: "WhatsApp Business" },
    { label: "Email (SMTP)" },
    { label: "AI narrator" },
    { label: "Accounting software" },
  ] },
  { label: "Developer", links: [
    { label: "API keys" },
    { label: "Webhooks" },
    { label: "Event log" },
  ] },
  { label: "Data", links: [
    { label: "Export workspace" },
    { label: "Retention & deletion" },
  ] },
];

const PARTNER_PERMS: { category: string; perms: { label: string; ok: boolean }[] }[] = [
  { category: "Clients", perms: [{ label: "View all", ok: true }, { label: "Edit assigned", ok: true }, { label: "Delete", ok: false }] },
  { category: "Filings", perms: [{ label: "Prepare", ok: true }, { label: "Review", ok: true }, { label: "Sign & file", ok: true }] },
  { category: "Documents", perms: [{ label: "Upload", ok: true }, { label: "Analyze", ok: true }, { label: "Delete", ok: false }] },
  { category: "Team", perms: [{ label: "View", ok: true }, { label: "Invite", ok: false }, { label: "Change roles", ok: false }] },
  { category: "Billing", perms: [{ label: "View", ok: false }, { label: "Change plan", ok: false }, { label: "Manage cards", ok: false }] },
  { category: "Audit log", perms: [{ label: "Read", ok: true }, { label: "Export", ok: false }, { label: "Delete lines", ok: false }] },
  { category: "AI narrator", perms: [{ label: "Trigger", ok: true }, { label: "Review draft", ok: true }, { label: "Change model", ok: false }] },
];

const ROLES: { name: RoleName; desc: string; count: string; expanded?: boolean }[] = [
  { name: "Owner", desc: "Ultimate control, cannot be removed", count: "1 member" },
  { name: "Admin", desc: "Manage team, plan, integrations, all clients", count: "1 member" },
  { name: "Partner", desc: "File returns, review, sign off", count: "3 members", expanded: true },
  { name: "Manager", desc: "Prepare returns, invite associates", count: "2 members" },
  { name: "Associate", desc: "Prepare returns, edit registers", count: "2 members" },
  { name: "External", desc: "Read-only for clients on their own data", count: "1 member" },
];

const LABEL: CSSProperties = {
  fontSize: 11,
  lineHeight: "16px",
  fontWeight: "var(--fw-medium)",
  letterSpacing: "var(--tr-label)",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

export default function SettingsPage() {
  const { users, invites, firm, loading, error, reload } = useSettingsData();
  const invite = useInviteMutation(reload);
  const memberRows = buildMemberRows(users, invites);
  const seats = seatsSummary(users, invites);

  return (
    <div style={{ display: "flex", flex: 1, minWidth: 0, minHeight: 0, background: "var(--bg)" }}>
      <SettingsNav firm={firm} memberCount={seats.used + seats.pending} />
      <main style={{ flex: 1, minWidth: 0, overflow: "auto", padding: 32 }}>
        <div style={{ maxWidth: 960, display: "flex", flexDirection: "column", gap: 24 }}>
          <SectionHeader firm={firm} />
          {error && <ErrorBanner message={`Could not load settings: ${error}`} onRetry={reload} />}
          {invite.error && <ErrorBanner message={`Invite failed: ${invite.error}`} onRetry={invite.clear} retryLabel="Dismiss" />}
          {invite.success && (
            <div role="status" style={{
              padding: "12px 16px",
              border: "1px solid var(--success)",
              borderRadius: "var(--radius-input)",
              background: "var(--success-soft)",
              color: "var(--success)",
              display: "flex", alignItems: "center", justifyContent: "space-between",
              gap: 12, fontSize: 13,
            }}>
              <span>{invite.success}</span>
              <button type="button" onClick={invite.clear} style={{
                border: "1px solid var(--success)", background: "transparent",
                color: "var(--success)", borderRadius: "var(--radius-chip)",
                padding: "4px 10px", fontSize: 12, fontWeight: 500, cursor: "pointer",
              }}>Dismiss</button>
            </div>
          )}
          <InviteBar seats={seats} onSend={invite.send} running={invite.running} />
          <TeamTable rows={memberRows} loading={loading && memberRows.length === 0} />
          <RolesMatrix />
          <SessionPolicy />
          <DangerZone firm={firm} />
        </div>
      </main>
    </div>
  );
}

/* --------------------------------- Sub-nav --------------------------------- */

function SettingsNav({ firm, memberCount }: { firm: FirmSettings | null; memberCount: number }) {
  return (
    <aside
      style={{
        width: 260,
        flex: "none",
        background: "var(--surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <div style={{ padding: "16px 16px 12px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 8 }}>
        <h2 style={{ margin: 0, fontSize: 15, lineHeight: "20px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          Settings
        </h2>
        <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
          {firm ? `${firm.name} · ${memberCount} member${memberCount === 1 ? "" : "s"} · ${firm.plan} plan` : "Loading firm…"}
        </span>
        <div
          className="v2-search-wrap"
          style={{
            marginTop: 4,
            boxSizing: "border-box",
            height: 32,
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 10px",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--radius-input)",
            background: "var(--bg)",
          }}
        >
          <SearchIcon size={14} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            placeholder="Search settings…"
            style={{
              flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent",
              font: `400 12px/16px var(--font-sans-v2)`, color: "var(--text-primary)",
            }}
          />
        </div>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: "12px 12px 16px", display: "flex", flexDirection: "column", gap: 16 }}>
        {NAV_GROUPS.map((g) => (
          <div key={g.label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ ...LABEL, padding: "4px 12px 8px" }}>{g.label}</span>
            {g.links.map((l) => (
              <a
                key={l.label}
                href="#"
                className={l.active ? "v2-focus-inset" : "v2-nav-link v2-focus"}
                style={{
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                  padding: "8px 12px",
                  borderRadius: "var(--radius-input)",
                  background: l.active ? "var(--accent-soft)" : "transparent",
                  color: l.active ? "var(--accent)" : "var(--text-secondary)",
                  fontSize: 13,
                  lineHeight: "20px",
                  fontWeight: l.active ? "var(--fw-medium)" : "var(--fw-regular)",
                  textDecoration: "none",
                  boxShadow: l.active ? "inset 3px 0 0 var(--accent)" : undefined,
                }}
              >
                {l.label}
              </a>
            ))}
          </div>
        ))}
      </div>
      <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--text-secondary)", textDecoration: "none" }}>Support</a>
          <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--text-secondary)", textDecoration: "none" }}>Docs ↗</a>
        </div>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>v · 2026.08.13</span>
      </div>
    </aside>
  );
}

/* --------------------------------- Section header --------------------------------- */

function SectionHeader({ firm }: { firm: FirmSettings | null }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 24 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: 620 }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Settings · Workspace{firm ? ` · ${firm.name}` : ""}
        </span>
        <h1
          style={{
            margin: 0,
            fontSize: "var(--fs-h1)",
            lineHeight: "var(--lh-h1)",
            fontWeight: "var(--fw-semi)",
            letterSpacing: "var(--tr-h1)",
            color: "var(--text-primary)",
          }}
        >
          Team &amp; permissions
        </h1>
        <p style={{ margin: 0, fontSize: 14, lineHeight: "20px", color: "var(--text-secondary)" }}>
          Invite teammates, manage roles, and control what each person can see or do.
          {firm && <> Plan: <strong style={{ fontWeight: 500, textTransform: "capitalize" }}>{firm.plan}</strong>.</>}
        </p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flex: "none" }}>
        <CheckCircleIcon size={14} style={{ color: "var(--success)" }} />
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          Changes save automatically · <a href="#" className="v2-focus" style={{ color: "var(--accent)", textDecoration: "none" }}>Logged in Audit log ↗</a>
        </span>
      </div>
    </div>
  );
}

/* --------------------------------- Invite bar --------------------------------- */

function InviteBar({
  seats, onSend, running,
}: {
  seats: { used: number; pending: number; label: string };
  onSend: (email: string, role: "admin" | "staff") => Promise<void>;
  running: boolean;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "staff">("staff");
  const disabled = running || email.trim().length === 0 || !email.includes("@");

  const submit = () => {
    if (disabled) return;
    onSend(email.trim(), role).then(() => setEmail(""));
  };

  return (
    <section
      style={{
        borderRadius: "var(--radius-app-card)",
        border: "1px solid var(--accent-panel-border)",
        borderLeft: "3px solid var(--accent)",
        background: "var(--accent-panel-bg)",
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <h3 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          Invite teammates
        </h3>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{seats.label}</span>
      </div>
      <form
        style={{ display: "flex", alignItems: "center", gap: 8 }}
        onSubmit={(e) => { e.preventDefault(); submit(); }}
      >
        <input
          type="email"
          placeholder="colleague@acmeca.in"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={running}
          style={{
            flex: 1,
            height: 36,
            padding: "0 12px",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
            outline: 0,
            font: `400 13px/20px var(--font-sans-v2)`,
            color: "var(--text-primary)",
          }}
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as "admin" | "staff")}
          disabled={running}
          style={{
            width: 140, height: 36, padding: "0 12px",
            border: "1px solid var(--border-strong)", borderRadius: "var(--radius-input)",
            background: "var(--surface)", color: "var(--text-primary)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
          }}
        >
          <option value="staff">Staff</option>
          <option value="admin">Admin</option>
        </select>
        <button
          type="submit"
          disabled={disabled}
          className="v2-btn-primary v2-focus"
          style={{
            height: 36,
            padding: "0 16px",
            border: 0,
            borderRadius: "var(--radius-input)",
            background: "var(--accent)",
            color: "var(--on-accent)",
            font: `500 13px/20px var(--font-sans-v2)`,
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.6 : 1,
          }}
        >
          {running ? "Sending…" : "Send invite"}
        </button>
      </form>
      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
        Invited users get an email · MFA is mandatory · Expires in 72h
      </span>
    </section>
  );
}

function SelectField({ children, width }: { children: React.ReactNode; width: number }) {
  return (
    <button
      type="button"
      className="v2-btn-secondary v2-focus"
      style={{
        width,
        height: 36,
        padding: "0 12px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        border: "1px solid var(--border-strong)",
        borderRadius: "var(--radius-input)",
        background: "var(--surface)",
        color: "var(--text-primary)",
        font: `500 13px/20px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
      <ChevronDownIcon size={14} style={{ color: "var(--text-muted)" }} />
    </button>
  );
}

/* --------------------------------- Team table --------------------------------- */

function TeamTable({ rows, loading }: { rows: MemberRow[]; loading: boolean }) {
  return (
    <section
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-app-card)",
        boxShadow: "var(--shadow-card)",
        overflow: "hidden",
      }}
    >
      <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
        <colgroup>
          <col style={{ width: 40 }} />
          <col style={{ width: 240 }} />
          <col style={{ width: 130 }} />
          <col style={{ width: 170 }} />
          <col style={{ width: 100 }} />
          <col style={{ width: 100 }} />
          <col style={{ width: 130 }} />
          <col style={{ width: 40 }} />
        </colgroup>
        <thead>
          <tr style={{ height: 44, borderBottom: "1px solid var(--border)" }}>
            <th style={{ padding: 0, textAlign: "center" }}>
              <input type="checkbox" aria-label="Select all" style={{ width: 14, height: 14, accentColor: "var(--accent)", cursor: "pointer" }} />
            </th>
            <Th sortable>Member</Th>
            <Th>Role</Th>
            <Th>Client scope</Th>
            <Th>Last active</Th>
            <Th>MFA</Th>
            <Th>Status</Th>
            <th style={{ padding: 0 }} />
          </tr>
        </thead>
        <tbody>
          {loading && rows.length === 0 ? (
            <tr><td colSpan={8} style={{ padding: 48, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>Loading members…</td></tr>
          ) : rows.length === 0 ? (
            <tr><td colSpan={8} style={{ padding: 0 }}><EmptyState message="No members yet." hint="Send an invite to get started." /></td></tr>
          ) : (
            rows.map((m, i) => (
              <MemberRow
                key={m.key}
                m={{
                  name: m.name, initials: m.initials, email: m.email,
                  subtitle: m.subtitle ?? undefined,
                  role: m.role, scopeMain: m.scopeMain, scopeMeta: m.scopeMeta,
                  lastActive: m.lastActive, mfa: m.mfa, status: m.status,
                  isOwner: m.isOwner,
                }}
                last={i === rows.length - 1}
              />
            ))
          )}
        </tbody>
      </table>
      <div style={{ height: 44, padding: "0 16px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {loading && rows.length === 0 ? "Loading…" : `Showing ${rows.length} of ${rows.length}`}
        </span>
        <button
          type="button"
          className="v2-hover-tint v2-focus"
          style={{
            height: 28,
            padding: "0 10px",
            display: "flex",
            alignItems: "center",
            gap: 6,
            border: 0,
            borderRadius: "var(--radius-input)",
            background: "transparent",
            color: "var(--text-secondary)",
            font: `500 12px/16px var(--font-sans-v2)`,
            cursor: "pointer",
          }}
        >
          Rows: 25
          <ChevronDownIcon size={12} />
        </button>
      </div>
    </section>
  );
}

function Th({ children, sortable }: { children: React.ReactNode; sortable?: boolean }) {
  return (
    <th
      style={{
        padding: "0 12px",
        textAlign: "left",
        font: `500 11px/16px var(--font-sans-v2)`,
        letterSpacing: "var(--tr-label)",
        textTransform: "uppercase",
        color: "var(--text-muted)",
      }}
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: sortable ? "pointer" : undefined }}>
        {children}
        {sortable && <ChevronDownIcon size={10} style={{ opacity: 0.5 }} />}
      </span>
    </th>
  );
}

function MemberRow({ m, last }: { m: Member; last: boolean }) {
  return (
    <tr className="v2-row" style={{ height: 56, borderBottom: last ? undefined : "1px solid var(--border)" }}>
      <td style={{ padding: 0, textAlign: "center" }}>
        <input type="checkbox" aria-label={`Select ${m.name}`} style={{ width: 14, height: 14, accentColor: "var(--accent)", cursor: "pointer" }} />
      </td>
      <td style={{ padding: "0 12px 0 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              width: 32, height: 32, flex: "none",
              borderRadius: "var(--radius-pill)",
              background: "var(--accent-soft)",
              color: "var(--accent)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, fontWeight: "var(--fw-semi)",
            }}
          >
            {m.initials}
          </span>
          <div style={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: 13, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.name}</span>
            <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {m.subtitle ? m.subtitle : m.email}
            </span>
          </div>
        </div>
      </td>
      <td style={{ padding: "0 12px" }}>
        <RoleChip role={m.role} />
      </td>
      <td style={{ padding: "0 12px" }}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 13, lineHeight: "18px", color: "var(--text-primary)" }}>{m.scopeMain}</span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{m.scopeMeta}</span>
        </div>
      </td>
      <td style={{ padding: "0 12px", fontSize: 12, color: "var(--text-secondary)" }}>{m.lastActive}</td>
      <td style={{ padding: "0 12px" }}><MfaCell kind={m.mfa} /></td>
      <td style={{ padding: "0 12px" }}><StatusCell status={m.status} /></td>
      <td style={{ padding: "0 8px", textAlign: "right" }}>
        {m.isOwner ? null : (
          <button
            type="button"
            aria-label="Row actions"
            className="v2-row-actions v2-focus"
            style={{
              width: 26, height: 26,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              border: 0, borderRadius: "var(--radius-chip)",
              background: "transparent",
              color: "var(--text-secondary)",
              cursor: "pointer",
            }}
          >
            <MoreHorizontalIcon size={14} />
          </button>
        )}
      </td>
    </tr>
  );
}

function RoleChip({ role }: { role: RoleName }) {
  const base: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 4,
    height: 22,
    padding: "0 8px",
    borderRadius: "var(--radius-chip)",
    fontSize: 11,
    fontWeight: "var(--fw-semi)",
    letterSpacing: "var(--tr-label)",
    textTransform: "uppercase",
  };
  if (role === "Owner") {
    return (
      <span style={{ ...base, background: "var(--accent)", color: "#fff" }}>
        <ShieldSvg />
        Owner
      </span>
    );
  }
  if (role === "Admin") return <span style={{ ...base, background: "var(--accent-soft)", color: "var(--accent)" }}>Admin</span>;
  if (role === "Partner") return <span style={{ ...base, background: "var(--success-soft)", color: "var(--success)" }}>Partner</span>;
  if (role === "Manager") return <span style={{ ...base, background: "var(--warning-soft)", color: "var(--warning)" }}>Manager</span>;
  if (role === "External") return <span style={{ ...base, background: "transparent", color: "var(--text-secondary)", border: "1px dashed var(--border-strong)" }}>External</span>;
  if (role === "Invited") return <span style={{ ...base, background: "transparent", color: "var(--text-secondary)", border: "1px dashed var(--border-strong)" }}>Invited</span>;
  if (role === "Staff") return <span style={{ ...base, background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>Staff</span>;
  return <span style={{ ...base, background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>Associate</span>;
}

function ShieldSvg() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3 4 6v6c0 4.5 3.4 8.4 8 9 4.6-.6 8-4.5 8-9V6z" />
    </svg>
  );
}

function MfaCell({ kind }: { kind: MfaKind }) {
  if (kind === "—") return <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>;
  if (kind === "Not set") {
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          padding: "3px 8px",
          borderRadius: "var(--radius-chip)",
          background: "var(--warning-soft)",
          color: "var(--warning)",
          fontSize: 11,
          fontWeight: "var(--fw-medium)",
        }}
      >
        <AlertTriangleIcon size={10} />
        Not set
      </span>
    );
  }
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "3px 8px",
        borderRadius: "var(--radius-chip)",
        background: "var(--success-soft)",
        color: "var(--success)",
        fontSize: 11,
        fontWeight: "var(--fw-medium)",
      }}
    >
      <CheckCircleIcon size={10} />
      {kind}
    </span>
  );
}

function StatusCell({ status }: { status: { label: string; kind: StatusKind } }) {
  const style: CSSProperties =
    status.kind === "active" ? { background: "var(--success-soft)", color: "var(--success)" } :
    status.kind === "pending" ? { background: "var(--warning-soft)", color: "var(--warning)" } :
    status.kind === "invited" ? { background: "var(--accent-soft)", color: "var(--accent)" } :
    { background: "var(--row-hover)", color: "var(--text-muted)" };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 8px",
        borderRadius: "var(--radius-chip)",
        fontSize: 11,
        fontWeight: "var(--fw-medium)",
        ...style,
      }}
    >
      {status.label}
    </span>
  );
}

/* --------------------------------- Roles & permissions --------------------------------- */

function RolesMatrix() {
  return (
    <section
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-app-card)",
        boxShadow: "var(--shadow-card)",
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h3 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
            Roles &amp; permissions
          </h3>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            6 built-in roles. Custom roles are available on the Enterprise plan.
          </span>
        </div>
        <button
          type="button"
          className="v2-btn-secondary v2-focus"
          style={{
            height: 32, padding: "0 12px", display: "flex", alignItems: "center", gap: 6,
            border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
            background: "var(--surface)", color: "var(--text-primary)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
          }}
        >
          <PlusIcon size={14} />
          Create custom role
        </button>
      </div>
      <div>
        {ROLES.map((r, i) => (
          <div key={r.name} style={{ borderTop: i === 0 ? undefined : "1px solid var(--border)" }}>
            <RoleRow role={r} />
            {r.expanded && <PartnerPermsGrid />}
          </div>
        ))}
      </div>
    </section>
  );
}

function RoleRow({ role }: { role: { name: RoleName; desc: string; count: string; expanded?: boolean } }) {
  return (
    <div
      style={{
        padding: "16px 20px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        background: role.expanded ? "var(--row-hover-accent)" : "var(--surface)",
        cursor: "pointer",
      }}
    >
      <RoleChip role={role.name} />
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <span style={{ fontSize: 13, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>
          {role.desc}
        </span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{role.count}</span>
      </div>
      <ChevronDownIcon size={16} style={{ color: "var(--text-muted)", transform: role.expanded ? "rotate(180deg)" : undefined }} />
    </div>
  );
}

function PartnerPermsGrid() {
  return (
    <div style={{ padding: "12px 20px 20px", background: "var(--row-hover-accent)", display: "flex", flexDirection: "column", gap: 8 }}>
      {PARTNER_PERMS.map((cat) => (
        <div key={cat.category} style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 12, alignItems: "start" }}>
          <span style={LABEL}>{cat.category}</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {cat.perms.map((p) => (
              <PermChip key={p.label} ok={p.ok}>{p.label}</PermChip>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function PermChip({ children, ok }: { children: React.ReactNode; ok: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        height: 22,
        padding: "0 8px",
        borderRadius: "var(--radius-chip)",
        background: ok ? "var(--success-soft)" : "transparent",
        border: ok ? "none" : "1px solid var(--border)",
        color: ok ? "var(--success)" : "var(--text-muted)",
        fontSize: 11,
        fontWeight: "var(--fw-medium)",
      }}
    >
      {ok ? "✓" : "✗"} {children}
    </span>
  );
}

/* --------------------------------- Session policy --------------------------------- */

function SessionPolicy() {
  return (
    <section
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-app-card)",
        boxShadow: "var(--shadow-card)",
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          Session &amp; sign-in policy
        </h3>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Applies to all members</span>
      </div>
      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 20 }}>
        <PolicyRow label="Session timeout">
          <div style={{ display: "flex", alignItems: "stretch", height: 32, border: "1px solid var(--border)", borderRadius: "var(--radius-input)", overflow: "hidden" }}>
            {["30 min", "2h", "8h", "24h"].map((opt, i) => (
              <button
                key={opt}
                type="button"
                className="v2-focus-inset"
                style={{
                  padding: "0 14px",
                  border: 0,
                  borderLeft: i === 0 ? undefined : "1px solid var(--border)",
                  background: opt === "8h" ? "var(--accent-soft)" : "transparent",
                  color: opt === "8h" ? "var(--accent)" : "var(--text-secondary)",
                  font: `500 12px/16px var(--font-sans-v2)`,
                  cursor: "pointer",
                }}
              >
                {opt}
              </button>
            ))}
          </div>
          <PolicyMeta>Members are signed out after this period of inactivity.</PolicyMeta>
        </PolicyRow>

        <PolicyRow label="Require MFA">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <ToggleSwitch on />
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "3px 8px",
                borderRadius: "var(--radius-chip)",
                background: "var(--warning-soft)",
                color: "var(--warning)",
                fontSize: 11,
                fontWeight: "var(--fw-medium)",
              }}
            >
              <AlertTriangleIcon size={10} />
              1 not compliant
            </span>
          </div>
          <PolicyMeta>Every member must enroll TOTP or a hardware key on next sign-in. 1 member has not enrolled yet.</PolicyMeta>
        </PolicyRow>

        <PolicyRow label="IP allow-list">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="text"
              defaultValue="203.0.113.0/24, 198.51.100.32"
              className="mono"
              style={{
                flex: 1,
                height: 32,
                padding: "0 10px",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-input)",
                background: "var(--surface)",
                outline: 0,
                color: "var(--text-primary)",
              }}
            />
            <button
              type="button"
              className="v2-btn-secondary v2-focus"
              style={{
                height: 32, padding: "0 14px",
                border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
                background: "var(--surface)", color: "var(--text-primary)",
                font: `500 12px/16px var(--font-sans-v2)`, cursor: "pointer",
              }}
            >
              Test
            </button>
          </div>
          <PolicyMeta>Only sessions from these IP ranges can sign in. Leave empty to allow any IP.</PolicyMeta>
        </PolicyRow>

        <PolicyRow label="SSO (SAML 2.0)">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              padding: "10px 12px",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-input)",
              background: "var(--bg)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: "var(--radius-pill)", background: "var(--success)" }} />
              <span style={{ fontSize: 13, color: "var(--text-primary)" }}>Google Workspace · connected</span>
            </div>
            <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>Configure ↗</a>
          </div>
          <PolicyMeta>Enterprise plan feature. Members will sign in via your identity provider only.</PolicyMeta>
        </PolicyRow>
      </div>
    </section>
  );
}

function PolicyRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 24, alignItems: "start" }}>
      <span style={{ fontSize: 13, fontWeight: "var(--fw-medium)", color: "var(--text-primary)", paddingTop: 6 }}>{label}</span>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>{children}</div>
    </div>
  );
}

function PolicyMeta({ children }: { children: React.ReactNode }) {
  return <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{children}</span>;
}

function ToggleSwitch({ on }: { on: boolean }) {
  return (
    <span
      role="switch"
      aria-checked={on}
      style={{
        width: 36,
        height: 20,
        borderRadius: "var(--radius-pill)",
        background: on ? "var(--accent)" : "var(--border-strong)",
        position: "relative",
        display: "inline-block",
        cursor: "pointer",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 2,
          left: on ? 18 : 2,
          width: 16,
          height: 16,
          borderRadius: "var(--radius-pill)",
          background: "#fff",
          transition: "left var(--dur-fast) var(--ease)",
        }}
      />
    </span>
  );
}

/* --------------------------------- Danger zone --------------------------------- */

function DangerZone({ firm }: { firm: FirmSettings | null }) {
  return (
    <section
      style={{
        borderRadius: "var(--radius-app-card)",
        border: "1px solid var(--danger)",
        borderLeft: "3px solid var(--danger)",
        background: "var(--danger-zone-bg)",
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--danger-zone-divider)", display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <AlertTriangleIcon size={18} style={{ color: "var(--danger)" }} />
          <h3 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--danger)" }}>
            Danger zone
          </h3>
        </div>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          These actions are irreversible or reduce your workspace. Owner-only.
        </span>
      </div>
      <DangerRow
        title="Transfer workspace ownership"
        desc="Move Owner role to another Admin. You will become an Admin."
        btn={<DangerOutlineBtn>Transfer ownership</DangerOutlineBtn>}
      />
      <DangerRow
        title="Revoke all team sessions"
        desc="Force-signout every member across every device. Members can sign back in with MFA."
        btn={<DangerOutlineBtn>Revoke all sessions</DangerOutlineBtn>}
      />
      <DangerRow
        title="Delete workspace"
        desc={`Permanently delete ${firm?.name ?? "this workspace"} and all client data. This cannot be undone. Requires typed confirmation.`}
        btn={<DangerSolidBtn>Delete workspace</DangerSolidBtn>}
        isLast
      />
    </section>
  );
}

function DangerRow({ title, desc, btn, isLast }: { title: string; desc: string; btn: React.ReactNode; isLast?: boolean }) {
  return (
    <div
      style={{
        padding: "16px 20px",
        borderBottom: isLast ? undefined : "1px solid var(--danger-zone-divider)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 13, fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>{title}</span>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{desc}</span>
      </div>
      {btn}
    </div>
  );
}

function DangerOutlineBtn({ children }: { children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="v2-focus"
      style={{
        height: 32,
        padding: "0 12px",
        border: "1px solid var(--danger)",
        borderRadius: "var(--radius-input)",
        background: "var(--surface)",
        color: "var(--danger)",
        font: `500 13px/20px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function DangerSolidBtn({ children }: { children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="v2-focus"
      style={{
        height: 32,
        padding: "0 12px",
        border: 0,
        borderRadius: "var(--radius-input)",
        background: "var(--danger)",
        color: "#fff",
        font: `500 13px/20px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}
