"use client";

import { CheckCircleIcon, AlertTriangleIcon } from "@/components/v2/icons";

/* --- reusable email envelope --------------------------------------------- */

function EmailShell({
  from, subject, preview, sent, children,
}: {
  from: string; subject: string; preview: string; sent: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* metadata strip */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12,
        }}>
          <div style={{
            fontSize: 13, fontWeight: 500, color: "var(--text-primary)",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>{from}</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", flex: "none" }}>{sent}</div>
        </div>
        <div style={{
          display: "flex", gap: 6, alignItems: "baseline", overflow: "hidden",
        }}>
          <span style={{
            fontSize: 13, fontWeight: 500, color: "var(--text-primary)",
            whiteSpace: "nowrap",
          }}>{subject}</span>
          <span style={{ color: "var(--text-muted)" }}>·</span>
          <span style={{
            fontSize: 13, color: "var(--text-muted)",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>{preview}</span>
        </div>
      </div>

      {/* envelope */}
      <div style={{
        width: "100%",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 12,
        boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
        overflow: "hidden",
      }}>
        <EmailHeader />
        {children}
        <EmailFooter />
      </div>
    </div>
  );
}

function EmailHeader() {
  return (
    <div style={{
      height: 72, padding: "0 32px",
      borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center", justifyContent: "space-between",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          width: 24, height: 24, borderRadius: 7, background: "var(--accent)",
          display: "grid", placeItems: "center",
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
      </div>
      <div style={{
        height: 32, padding: "0 12px",
        border: "1px solid var(--border)", borderRadius: 8,
        display: "inline-flex", alignItems: "center",
        fontSize: 12, color: "var(--text-secondary)",
      }}>
        For · Acme CA
      </div>
    </div>
  );
}

function EmailFooter({ line }: { line?: string } = {}) {
  return (
    <div style={{
      padding: "16px 32px",
      borderTop: "1px solid var(--border)",
      textAlign: "center",
      fontSize: 12, color: "var(--text-muted)",
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      <div>
        {line ?? "You're receiving this because you're an Owner of Acme CA."}
      </div>
      <div style={{ display: "flex", justifyContent: "center", gap: 8 }}>
        <a href="#" style={{ color: "inherit", textDecoration: "none" }}>Manage notifications</a>
        <span>·</span>
        <a href="#" style={{ color: "inherit", textDecoration: "none" }}>Unsubscribe</a>
        <span>·</span>
        <a href="#" style={{ color: "inherit", textDecoration: "none" }}>View in browser</a>
      </div>
    </div>
  );
}

/* --- shared bits inside body -------------------------------------------- */

function KvRow({ label, value, mono, valueColor, valueWeight }: {
  label: string; value: string;
  mono?: boolean; valueColor?: string; valueWeight?: number;
}) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "baseline",
      padding: "12px 0", borderTop: "1px solid var(--border)",
      fontSize: 13,
    }}>
      <div style={{ color: "var(--text-muted)" }}>{label}</div>
      <div style={{
        color: valueColor ?? "var(--text-primary)",
        fontWeight: valueWeight ?? 400,
        fontFamily: mono ? "var(--font-mono-v2)" : undefined,
        textAlign: "right",
      }}>{value}</div>
    </div>
  );
}

function PrimaryBtn({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      height: 44, marginTop: 24,
      background: "var(--accent)", color: "#fff",
      borderRadius: 8,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 15, fontWeight: 500, cursor: "pointer",
    }}>{children}</div>
  );
}

function SecondaryBtn({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      flex: 1, height: 44,
      background: "var(--surface)", color: "var(--text-primary)",
      border: "1px solid var(--border-strong)", borderRadius: 8,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 14, fontWeight: 500, cursor: "pointer",
    }}>{children}</div>
  );
}

/* --- Email 1: Filing Due (warning) -------------------------------------- */

function EmailDue() {
  return (
    <EmailShell
      from="From: Niyam AI <notifications@niyam.ai>"
      sent="13 Aug 2026, 09:14 IST"
      subject="GSTR-3B for Ramesh Textiles is due in 7 days"
      preview="84 clients need GSTR-3B filed by 20 Aug. 42 are ready."
    >
      <div style={{ padding: 32 }}>
        {/* alert */}
        <div style={{
          padding: 16, borderRadius: 10,
          background: "var(--warning-soft)",
          borderLeft: "3px solid var(--warning)",
          display: "flex", alignItems: "center", gap: 12, justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ color: "var(--warning)" }}><AlertTriangleIcon size={16} /></span>
            <div style={{ fontSize: 18, fontWeight: 600, color: "var(--warning)" }}>
              Due in 7 days
            </div>
          </div>
          <div style={{
            height: 24, padding: "0 8px",
            background: "var(--surface)", color: "var(--warning)",
            border: "1px solid var(--warning)",
            borderRadius: 999,
            display: "inline-flex", alignItems: "center",
            fontSize: 12, fontWeight: 500,
          }}>20 Aug 2026</div>
        </div>

        <div style={{
          marginTop: 24, fontSize: 24, lineHeight: "32px", fontWeight: 600,
          letterSpacing: "-0.01em", color: "var(--text-primary)",
        }}>GSTR-3B · Ramesh Textiles Pvt Ltd</div>

        <div style={{
          marginTop: 16, fontSize: 15, lineHeight: "24px", color: "var(--text-secondary)",
        }}>
          You have 84 GSTR-3B returns due on 20 Aug. 42 are already validated
          and ready to review. Ramesh Textiles is the largest by value.
        </div>

        <div style={{ marginTop: 24 }}>
          <KvRow label="GSTIN" value="29AAAAA0000A1Z5" mono />
          <KvRow label="Tax payable (est.)" value="₹42,68,780" valueWeight={500} />
          <KvRow label="Blockers" value="2 open" valueColor="var(--danger)" valueWeight={500} />
        </div>

        <PrimaryBtn>Review and file →</PrimaryBtn>

        <div style={{
          marginTop: 16, textAlign: "center",
          fontSize: 13, fontWeight: 500, color: "var(--accent)",
        }}>See all 84 returns due 20 Aug →</div>
      </div>
    </EmailShell>
  );
}

/* --- Email 2: Filing Complete (success) --------------------------------- */

function EmailFiled() {
  return (
    <EmailShell
      from="From: Niyam AI <notifications@niyam.ai>"
      sent="12 Aug 2026, 11:42 IST"
      subject="Filed · GSTR-1 · Ramesh Textiles · Jul 2026"
      preview="Ack ID 296130400012345. No client action needed."
    >
      <div style={{ padding: 32 }}>
        <div style={{
          padding: 16, borderRadius: 10,
          background: "var(--success-soft)",
          borderLeft: "3px solid var(--success)",
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <span style={{ color: "var(--success)" }}><CheckCircleIcon size={18} /></span>
          <div style={{ fontSize: 18, fontWeight: 600, color: "var(--success)" }}>
            Filed successfully
          </div>
        </div>

        <div style={{
          marginTop: 24, fontSize: 24, lineHeight: "32px", fontWeight: 600,
          letterSpacing: "-0.01em", color: "var(--text-primary)",
        }}>GSTR-1 · July 2026</div>

        <div style={{
          marginTop: 16, fontSize: 15, lineHeight: "24px", color: "var(--text-secondary)",
        }}>
          Filed for Ramesh Textiles Pvt Ltd at 11:42 AM IST. GSTN has issued
          an acknowledgement — no further action needed.
        </div>

        <div style={{ marginTop: 24 }}>
          <KvRow label="Filed by" value="Priya Mehta · Manager" />
          <KvRow label="Filed at" value="12 Aug 2026, 11:42 IST" />
          <KvRow label="Ack ID" value="296130400012345" mono />
          <KvRow label="Return value" value="₹42,68,780 outward tax" valueWeight={500} />
        </div>

        <div style={{ marginTop: 24, display: "flex", gap: 8 }}>
          <SecondaryBtn>Download PDF</SecondaryBtn>
          <SecondaryBtn>View in Niyam</SecondaryBtn>
        </div>

        <div style={{
          marginTop: 16, fontSize: 13, color: "var(--text-muted)",
        }}>
          Every filing is version-stamped and reachable from the client&apos;s Filings tab.
        </div>
      </div>
    </EmailShell>
  );
}

/* --- Email 3: Workspace Invite (neutral) -------------------------------- */

function EmailInvite() {
  return (
    <EmailShell
      from="From: Niyam AI <notifications@niyam.ai>"
      sent="13 Aug 2026, 07:20 IST"
      subject="Priya invited you to Acme CA on Niyam AI"
      preview="Accept your invite to get started. Expires in 72 hours."
    >
      <div style={{ padding: 32 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10,
          background: "var(--accent-soft)", color: "var(--accent)",
          display: "grid", placeItems: "center",
          fontSize: 14, fontWeight: 600, letterSpacing: "0.02em",
        }}>AC</div>

        <div style={{
          marginTop: 24, fontSize: 24, lineHeight: "32px", fontWeight: 600,
          letterSpacing: "-0.01em", color: "var(--text-primary)",
        }}>You&apos;ve been invited to Acme CA.</div>

        <div style={{
          marginTop: 16, fontSize: 15, lineHeight: "24px", color: "var(--text-secondary)",
        }}>
          Priya Mehta invited you to join the Acme CA workspace on Niyam AI
          as an Associate. You&apos;ll be assigned 24 clients.
        </div>

        <div style={{
          marginTop: 24, padding: 16, borderRadius: 10,
          background: "var(--bg)", border: "1px solid var(--border)",
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 999,
            background: "var(--accent-soft)", color: "var(--accent)",
            display: "grid", placeItems: "center",
            fontSize: 12, fontWeight: 600,
          }}>PM</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{
              fontSize: 14, lineHeight: "20px", fontWeight: 500, color: "var(--text-primary)",
            }}>Priya Mehta · Manager, Acme CA</div>
            <div style={{
              fontSize: 12, lineHeight: "16px", color: "var(--text-muted)",
            }}>priya@acmeca.in</div>
          </div>
        </div>

        <PrimaryBtn>Accept invite</PrimaryBtn>
        <div style={{
          marginTop: 8, textAlign: "center",
          fontSize: 11, color: "var(--text-muted)",
        }}>expires in 72h</div>

        <div style={{
          marginTop: 16, fontSize: 13, color: "var(--text-secondary)",
        }}>
          Not expecting this? You can safely ignore this email.
          The invite will expire automatically.
        </div>
      </div>
    </EmailShell>
  );
}

/* --- Email 4: Weekly Summary (digest) ----------------------------------- */

function KpiCell({ label, value, change, changeColor }: {
  label: string; value: string; change: string; changeColor: string;
}) {
  return (
    <div style={{
      padding: 12, minHeight: 88,
      border: "1px solid var(--border)", borderRadius: 10,
      display: "flex", flexDirection: "column", justifyContent: "space-between",
    }}>
      <div style={{
        fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
        textTransform: "uppercase", color: "var(--text-muted)",
      }}>{label}</div>
      <div style={{
        fontSize: 24, fontWeight: 600, color: "var(--text-primary)", lineHeight: 1.1,
      }}>{value}</div>
      <div style={{ fontSize: 12, color: changeColor }}>{change}</div>
    </div>
  );
}

function ReviewRow({ badge, title, status, statusColor }: {
  badge: string; title: string; status: string; statusColor: string;
}) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "10px 0", borderBottom: "1px solid var(--border)",
    }}>
      <span style={{
        height: 20, padding: "0 6px", flex: "none",
        border: "1px solid var(--border)", borderRadius: 6,
        display: "inline-flex", alignItems: "center",
        fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
        color: "var(--text-secondary)",
      }}>{badge}</span>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{
          fontSize: 14, lineHeight: "18px", fontWeight: 500, color: "var(--text-primary)",
        }}>{title}</div>
        <div style={{ fontSize: 12, lineHeight: "16px", color: statusColor }}>{status}</div>
      </div>
      <a href="#" style={{
        fontSize: 12, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
      }}>Review →</a>
    </div>
  );
}

function EmailWeekly() {
  return (
    <EmailShell
      from="From: Niyam AI <notifications@niyam.ai>"
      sent="10 Aug 2026, 09:00 IST"
      subject="Week 33 · Acme CA · 47 filings, 5 at risk"
      preview="96.2% on-time. Vikram H. cleared 12 returns. 3 need your review."
    >
      <div style={{ padding: 32 }}>
        <div style={{
          fontSize: 24, lineHeight: "32px", fontWeight: 600,
          letterSpacing: "-0.01em", color: "var(--text-primary)",
        }}>This week at Acme CA</div>

        <div style={{ marginTop: 8, fontSize: 13, color: "var(--text-muted)" }}>
          Aug 5 – Aug 12, 2026 · 142 clients
        </div>

        <div style={{
          marginTop: 24, display: "grid",
          gridTemplateColumns: "1fr 1fr", gap: 8,
        }}>
          <KpiCell label="FILINGS COMPLETED" value="47"    change="+3 vs last week"   changeColor="var(--success)" />
          <KpiCell label="ON-TIME RATE"      value="96.2%" change="−0.6pp"            changeColor="var(--danger)" />
          <KpiCell label="AT-RISK CLIENTS"   value="5"     change="+2"                changeColor="var(--warning)" />
          <KpiCell label="PENDING REVIEW"    value="3"     change="assigned to you"   changeColor="var(--accent)" />
        </div>

        <div style={{
          marginTop: 24,
          fontSize: 18, fontWeight: 600, color: "var(--text-primary)",
        }}>Needs your review</div>

        <div style={{ marginTop: 8 }}>
          <ReviewRow badge="GST-3B" title="Ramesh Textiles Pvt Ltd" status="Blocker: HSN"  statusColor="var(--danger)" />
          <ReviewRow badge="GST-1"  title="Nova Exports LLP"        status="Late file · 1d" statusColor="var(--warning)" />
          <ReviewRow badge="AOC-4"  title="Meridian Logistics LLP"  status="Overdue 7d"     statusColor="var(--danger)" />
        </div>

        <PrimaryBtn>Open your dashboard →</PrimaryBtn>

        <div style={{
          marginTop: 16, textAlign: "center",
          fontSize: 13, color: "var(--text-muted)",
        }}>
          Delivered every Monday at 09:00 IST. Adjust in Settings → Notifications.
        </div>
      </div>
    </EmailShell>
  );
}

/* --- page ---------------------------------------------------------------- */

export default function EmailsPage() {
  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg)",
      padding: "48px 32px 96px",
    }}>
      <div style={{ maxWidth: 1328, margin: "0 auto" }}>
        <div style={{ marginBottom: 32 }}>
          <div style={{
            fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
            textTransform: "uppercase", color: "var(--text-muted)",
          }}>Transactional email templates</div>
          <h1 style={{
            margin: "8px 0 0 0",
            fontSize: 32, lineHeight: "40px", fontWeight: 600,
            letterSpacing: "-0.02em", color: "var(--text-primary)",
          }}>4 emails your CA firm will actually send.</h1>
          <div style={{ marginTop: 8, fontSize: 14, color: "var(--text-secondary)" }}>
            Each envelope is 600px wide, brand-locked, and MFA-consistent with in-app tone.
          </div>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 600px))",
          gap: 64,
          justifyContent: "center",
        }}>
          <EmailDue />
          <EmailFiled />
          <EmailInvite />
          <EmailWeekly />
        </div>
      </div>
    </div>
  );
}
