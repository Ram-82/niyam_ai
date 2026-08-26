"use client";

import { useState } from "react";
import {
  CalendarIcon,
  ChevronDownIcon,
  DownloadIcon,
  MoreHorizontalIcon,
  SearchIcon,
  SparklesIcon,
  ArrowUpIcon,
  PlusIcon,
} from "@/components/v2/icons";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import {
  buildMonthlyStacks,
  buildPrevTotals,
  computeKpis,
  monthsWindowLabel,
  useReportsData,
  type MonthlyStack,
  type MonthlyTimeliness,
  type ReportsKpi,
  type TimelinessResponse,
} from "./useReportsData";

// team performance rows
type Row = {
  name: string; role: "Partner" | "Manager" | "Associate";
  tenure: string;
  filings: number; sparkline: number[];
  onTime: number;   // percent
  median: number;   // days
  itc: number;      // in ₹ crore
  util: number;     // percent 0-100
};

const TEAM: Row[] = [
  { name: "Arjun Desai", role: "Partner", tenure: "since Jun 2023",
    filings: 248, sparkline: [18, 21, 19, 24, 22, 26, 23, 27, 25, 28, 24, 26],
    onTime: 98.4, median: 2.1, itc: 1.42, util: 84 },
  { name: "Priya Mehta", role: "Manager", tenure: "since Feb 2022",
    filings: 412, sparkline: [30, 32, 34, 36, 33, 38, 35, 39, 41, 40, 38, 42],
    onTime: 97.8, median: 2.6, itc: 2.18, util: 92 },
  { name: "Kavya S.", role: "Associate", tenure: "since Aug 2024",
    filings: 386, sparkline: [26, 28, 30, 34, 32, 36, 33, 35, 34, 38, 36, 39],
    onTime: 93.5, median: 4.1, itc: 1.02, util: 76 },
  { name: "Rohit Sen", role: "Manager", tenure: "since Mar 2023",
    filings: 324, sparkline: [22, 24, 25, 28, 26, 30, 27, 31, 29, 32, 30, 34],
    onTime: 96.2, median: 3.0, itc: 1.28, util: 81 },
  { name: "Neha Gupta", role: "Associate", tenure: "since Jan 2025",
    filings: 291, sparkline: [20, 22, 23, 25, 24, 27, 25, 28, 26, 29, 27, 30],
    onTime: 94.8, median: 3.8, itc: 0.94, util: 73 },
  { name: "Vikram Hegde", role: "Associate", tenure: "since Nov 2025",
    filings: 186, sparkline: [12, 14, 13, 16, 15, 17, 16, 18, 17, 19, 18, 20],
    onTime: 95.1, median: 4.4, itc: 0.61, util: 62 },
];

// right rail: reports library
const LIB = [
  {
    group: "Recently viewed",
    items: [
      { title: "Filing performance", meta: "Firm analytics · updated 2 min ago", active: true },
      { title: "ITC leakage — Aug 2026", meta: "Firm analytics · updated 1 hr ago" },
      { title: "Ramesh Textiles · Q1 scorecard", meta: "Client report · updated yesterday" },
    ],
  },
  {
    group: "Firm analytics",
    items: [
      { title: "Filing performance", meta: "Throughput, on-time, turnaround", spark: [12, 14, 13, 16, 15, 17, 16, 18] },
      { title: "Revenue snapshot", meta: "Fees billed, WIP, receivables", spark: [10, 11, 13, 12, 15, 14, 16, 18] },
      { title: "Team productivity", meta: "Utilisation, ITC recovered, workload", spark: [22, 24, 23, 26, 25, 28, 27, 29] },
      { title: "Practice health", meta: "Risk-weighted KPIs, board pack", spark: [8, 9, 11, 10, 12, 13, 12, 14] },
    ],
  },
  {
    group: "Client reports",
    items: [
      { title: "Client scorecard", meta: "Per-client health · exports as PDF" },
      { title: "Client grid report", meta: "Multi-client matrix · sortable, printable" },
    ],
  },
];

/* --- small helpers -------------------------------------------------------- */

function fmtInr(cr: number) {
  return `₹${cr.toFixed(2)} Cr`;
}

function Initials({ name }: { name: string }) {
  const parts = name.split(" ");
  const chars = ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
  return (
    <div style={{
      width: 32, height: 32, borderRadius: 8,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--accent-soft)", color: "var(--accent)",
      fontSize: 12, fontWeight: 600, letterSpacing: "0.02em", flex: "0 0 auto",
    }}>
      {chars}
    </div>
  );
}

/* --- sparkline component (60×h SVG) --------------------------------------- */

function Sparkline({
  data, width = 60, height = 16,
  stroke = "var(--accent)", strokeWidth = 1.5, fill = false,
}: { data: number[]; width?: number; height?: number;
    stroke?: string; strokeWidth?: number; fill?: boolean }) {
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const step = width / (data.length - 1);
  const pts = data.map((v, i) => {
    const x = i * step;
    const y = height - 2 - ((v - min) / span) * (height - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      {fill && (
        <polygon
          points={`0,${height} ${pts} ${width},${height}`}
          fill={stroke} fillOpacity={0.12}
        />
      )}
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth={strokeWidth}
        strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* --- stacked bar chart ---------------------------------------------------- */

function StackedBars({ stacks, prevTotals }: { stacks: MonthlyStack[]; prevTotals: number[] }) {
  const allTotals = [...stacks.map((s) => s.total), ...prevTotals];
  const rawMax = Math.max(...allTotals, 10);
  // Round up to a friendly axis max.
  const step = rawMax <= 50 ? 10 : rawMax <= 200 ? 50 : 100;
  const barMax = Math.ceil(rawMax / step) * step || step;
  const barH = 208;
  const gridSteps = 4;
  const axisTicks = Array.from({ length: gridSteps + 1 }, (_, i) => Math.round(barMax - (i * barMax) / gridSteps));
  return (
    <div style={{ display: "flex", gap: 24, alignItems: "stretch" }}>
      {/* y-axis */}
      <div style={{
        display: "flex", flexDirection: "column", justifyContent: "space-between",
        paddingTop: 4, paddingBottom: 24, width: 32,
        fontSize: 11, color: "var(--text-muted)", textAlign: "right",
      }}>
        {axisTicks.map((v, i) => <div key={i}>{v}</div>)}
      </div>
      {/* bars */}
      <div style={{ flex: 1, position: "relative", minWidth: 0 }}>
        {/* gridlines */}
        <div style={{ position: "absolute", inset: `4px 0 24px 0`, pointerEvents: "none" }}>
          {[0, 1, 2, 3, 4].map(i => (
            <div key={i} style={{
              position: "absolute", left: 0, right: 0,
              top: `${(i * (barH)) / 4}px`,
              height: 1,
              background: i === 4 ? "var(--border-strong)" : "var(--border)",
              opacity: i === 4 ? 1 : 0.6,
            }} />
          ))}
        </div>
        <div style={{
          position: "relative", height: barH + 4, display: "flex",
          alignItems: "flex-end", gap: 8, padding: "4px 0 0 0",
        }}>
          {stacks.map((s, i) => {
            const total = s.total;
            const prev = prevTotals[i] ?? 0;
            const segH = (v: number) => (v / barMax) * barH;
            return (
              <div key={i} style={{
                flex: 1, display: "flex", gap: 4, alignItems: "flex-end",
                justifyContent: "center", position: "relative", height: barH,
              }}>
                {/* previous period outline */}
                {prev > 0 && (
                  <div style={{
                    position: "absolute", left: "50%", transform: "translateX(-50%)",
                    bottom: 0, width: 28, height: (prev / barMax) * barH,
                    border: "1px dashed var(--border-strong)",
                    borderRadius: "6px 6px 0 0",
                    pointerEvents: "none",
                  }} />
                )}
                {/* current stack */}
                <div style={{
                  width: 20, display: "flex", flexDirection: "column-reverse",
                  borderRadius: "6px 6px 0 0", overflow: "hidden",
                  minHeight: total > 0 ? 2 : 0,
                }}>
                  <div style={{ height: segH(s.gstr1), background: "var(--accent)" }} title={`GSTR-1 ${s.gstr1}`} />
                  <div style={{ height: segH(s.gstr3b), background: "var(--success)" }} title={`GSTR-3B ${s.gstr3b}`} />
                  <div style={{ height: segH(s.other), background: "var(--text-secondary)" }} title={`Other ${s.other}`} />
                </div>
                {total > 0 && (
                  <div style={{
                    position: "absolute", bottom: "100%", left: "50%",
                    transform: "translateX(-50%)", marginBottom: 2,
                    fontSize: 10, color: "var(--text-muted)", fontWeight: 500,
                    whiteSpace: "nowrap",
                  }}>{total}</div>
                )}
              </div>
            );
          })}
        </div>
        {/* x-axis labels */}
        <div style={{
          display: "flex", gap: 8, marginTop: 8, height: 16,
          fontSize: 11, color: "var(--text-muted)",
        }}>
          {stacks.map((s) => (
            <div key={s.period} style={{ flex: 1, textAlign: "center" }}>{s.label}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* --- multi-line area chart (filing timeliness) ---------------------------- */

/** On-time percentage per month per return type.
 *  Months with zero filings render as gaps (broken polyline) — better than
 *  charting 0% and pretending the firm was 100% late. */
function TimelinessChart({ data, loading }: { data: TimelinessResponse | null; loading: boolean }) {
  if (loading && data === null) {
    return <div style={{ height: 228, display: "grid", placeItems: "center", color: "var(--text-muted)", fontSize: 13 }}>Loading timeliness…</div>;
  }
  if (!data || data.months.length === 0) {
    return <EmptyState message="No timeliness data yet." hint="Once filings are marked filed the chart will populate." />;
  }
  const anyFiled = data.total_filed > 0;
  if (!anyFiled) {
    return <EmptyState message="No filings marked filed in the last 12 months." hint="On-time % becomes available after the first mark-filed action." />;
  }

  const w = 900, h = 220;
  const months = data.months;
  const yMin = 0, yMax = 100;
  const stepX = months.length > 1 ? w / (months.length - 1) : 0;

  type PointList = Array<{ x: number; y: number } | null>;
  const buildPoints = (pick: (m: MonthlyTimeliness) => number | null): PointList =>
    months.map((m, i) => {
      const v = pick(m);
      if (v === null) return null;
      const x = i * stepX;
      const y = h - ((v - yMin) / (yMax - yMin)) * (h - 24) - 8;
      return { x, y };
    });

  const pctOrNull = (on: number, total: number) => (total === 0 ? null : (on / total) * 100);

  const series: { key: string; label: string; color: string; points: PointList }[] = [
    {
      key: "gstr1",
      label: "GSTR-1",
      color: "var(--accent)",
      points: buildPoints((m) => pctOrNull(m.gstr1_on_time, m.gstr1_filed)),
    },
    {
      key: "gstr3b",
      label: "GSTR-3B",
      color: "var(--success)",
      points: buildPoints((m) => pctOrNull(m.gstr3b_on_time, m.gstr3b_filed)),
    },
  ];

  // Break the polyline at NULLs so months with no data don't get bridged.
  const pointsToSegments = (pts: PointList): string[] => {
    const segs: string[] = [];
    let cur: string[] = [];
    for (const p of pts) {
      if (p === null) {
        if (cur.length > 1) segs.push(cur.join(" "));
        cur = [];
      } else {
        cur.push(`${p.x.toFixed(1)},${p.y.toFixed(1)}`);
      }
    }
    if (cur.length > 1) segs.push(cur.join(" "));
    return segs;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 16 }}>
        <div style={{
          display: "flex", flexDirection: "column", justifyContent: "space-between",
          paddingBottom: 24, width: 36, fontSize: 11, color: "var(--text-muted)",
          textAlign: "right",
        }}>
          <div>100%</div>
          <div>75%</div>
          <div>50%</div>
          <div>25%</div>
          <div>0%</div>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <svg viewBox={`0 0 ${w} ${h + 8}`} width="100%" height={h + 8}
               preserveAspectRatio="none" style={{ display: "block" }}>
            {[0, 1, 2, 3, 4].map(i => (
              <line key={i}
                x1={0} x2={w}
                y1={(i * (h - 8)) / 4 + 4}
                y2={(i * (h - 8)) / 4 + 4}
                stroke="var(--border)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
                opacity={i === 4 ? 1 : 0.5}
              />
            ))}
            {series.map(s => (
              <g key={s.key}>
                {pointsToSegments(s.points).map((seg, i) => (
                  <polyline
                    key={i}
                    points={seg}
                    fill="none"
                    stroke={s.color}
                    strokeWidth={2}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
                {s.points.map((p, i) =>
                  p === null ? null : (
                    <circle key={`d-${s.key}-${i}`} cx={p.x} cy={p.y} r={2.5} fill={s.color} vectorEffect="non-scaling-stroke" />
                  )
                )}
              </g>
            ))}
          </svg>
          <div style={{
            display: "flex", marginTop: 8, height: 16,
            fontSize: 11, color: "var(--text-muted)",
          }}>
            {months.map((m) => (
              <div key={m.period} style={{ flex: 1, textAlign: "center" }}>{m.label.slice(0, 3)}</div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "right" }}>
        {data.total_filed} filing{data.total_filed === 1 ? "" : "s"} in window · {data.total_on_time} on-time (
        {data.total_filed > 0 ? `${((data.total_on_time / data.total_filed) * 100).toFixed(1)}%` : "—"})
      </div>
    </div>
  );
}

/* --- KPI cell ------------------------------------------------------------- */

function KpiCell({
  label, value, delta, deltaTone, spark, sparkTone,
}: {
  label: string; value: string;
  delta: string; deltaTone: "success" | "danger" | "accent";
  spark: number[];
  sparkTone: "success" | "danger" | "accent" | "warning";
}) {
  const toneMap = {
    success: { bg: "var(--success-soft)", fg: "var(--success)" },
    danger:  { bg: "var(--danger-soft)",  fg: "var(--danger)" },
    accent:  { bg: "var(--accent-soft)",  fg: "var(--accent)" },
  };
  const strokeMap = {
    success: "var(--success)",
    danger:  "var(--danger)",
    accent:  "var(--accent)",
    warning: "var(--warning)",
  };
  const t = toneMap[deltaTone];
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 10, padding: 20, minHeight: 128,
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      <div style={{
        fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em",
        color: "var(--text-muted)", fontWeight: 500,
      }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 600, color: "var(--text-primary)",
                    letterSpacing: "-0.01em", lineHeight: 1.1 }}>
        {value}
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    marginTop: "auto" }}>
        <div style={{
          background: t.bg, color: t.fg,
          padding: "2px 8px", borderRadius: 999, fontSize: 12, fontWeight: 500,
        }}>{delta}</div>
        <Sparkline data={spark} stroke={strokeMap[sparkTone]} width={72} height={20} fill />
      </div>
    </div>
  );
}

/* --- utilisation bar ------------------------------------------------------ */

function UtilBar({ v }: { v: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
      <div style={{
        width: 88, height: 6, borderRadius: 999,
        background: "var(--border)", overflow: "hidden",
      }}>
        <div style={{
          width: `${v}%`, height: "100%", background: "var(--accent)",
        }} />
      </div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", width: 32, textAlign: "right" }}>
        {v}%
      </div>
    </div>
  );
}

/* --- team table ---------------------------------------------------------- */

function TeamTable() {
  const th: React.CSSProperties = {
    textAlign: "right", padding: "10px 12px",
    fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em",
    color: "var(--text-muted)", fontWeight: 500,
    borderBottom: "1px solid var(--border)",
  };
  const td: React.CSSProperties = {
    textAlign: "right", padding: "16px 12px",
    fontSize: 13, color: "var(--text-primary)", fontWeight: 500,
    borderBottom: "1px solid var(--border)", verticalAlign: "middle",
  };
  const totals = TEAM.reduce((a, r) => ({
    filings: a.filings + r.filings,
    itc: a.itc + r.itc,
  }), { filings: 0, itc: 0 });

  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 10, overflow: "hidden",
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "20px 24px",
      }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
            Team performance
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
            Sep 2025 – Aug 2026 · 6 members · 1,847 filings
          </div>
        </div>
        <button className="v2-btn-secondary" style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "6px 12px", fontSize: 12, fontWeight: 500,
          color: "var(--text-secondary)",
          background: "transparent", border: "1px solid var(--border)",
          borderRadius: 8, cursor: "pointer",
        }}>
          Sort by throughput
          <ChevronDownIcon size={12} />
        </button>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead style={{ background: "var(--bg)" }}>
          <tr>
            <th style={{ ...th, textAlign: "left", width: 260 }}>Member</th>
            <th style={{ ...th, textAlign: "left", width: 110 }}>Role</th>
            <th style={{ ...th, width: 170 }}>Filings completed</th>
            <th style={{ ...th, width: 110 }}>On-time</th>
            <th style={{ ...th, width: 170 }}>Median turnaround</th>
            <th style={{ ...th, width: 160 }}>ITC recovered</th>
            <th style={{ ...th }}>Utilisation</th>
          </tr>
        </thead>
        <tbody>
          {TEAM.map((r, i) => {
            const onTimeTone = r.onTime >= 96 ? "var(--success)"
                              : r.onTime >= 94 ? "var(--warning)"
                              : "var(--danger)";
            const medTone = r.median <= 2.5 ? "var(--success)"
                          : r.median <= 3.5 ? "var(--text-primary)"
                          : "var(--warning)";
            return (
              <tr key={i} className="v2-row">
                <td style={{ ...td, textAlign: "left" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <Initials name={r.name} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
                        {r.name}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                        {r.tenure}
                      </div>
                    </div>
                  </div>
                </td>
                <td style={{ ...td, textAlign: "left", color: "var(--text-secondary)", fontWeight: 400 }}>
                  {r.role}
                </td>
                <td style={td}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "flex-end" }}>
                    <Sparkline data={r.sparkline} width={60} height={12} />
                    <div style={{ width: 40, textAlign: "right" }}>{r.filings}</div>
                  </div>
                </td>
                <td style={{ ...td, color: onTimeTone }}>{r.onTime.toFixed(1)}%</td>
                <td style={{ ...td, color: medTone }}>{r.median.toFixed(1)}d</td>
                <td style={td}>{fmtInr(r.itc)}</td>
                <td style={td}><UtilBar v={r.util} /></td>
              </tr>
            );
          })}
          <tr style={{ background: "var(--bg)" }}>
            <td style={{ ...td, textAlign: "left",
                         fontWeight: 600, color: "var(--text-primary)",
                         borderBottom: "none" }}>
              Team avg
            </td>
            <td style={{ ...td, textAlign: "left", color: "var(--text-muted)",
                         fontWeight: 400, borderBottom: "none" }}>—</td>
            <td style={{ ...td, borderBottom: "none" }}>{totals.filings.toLocaleString()}</td>
            <td style={{ ...td, borderBottom: "none" }}>96.2%</td>
            <td style={{ ...td, borderBottom: "none" }}>3.3d</td>
            <td style={{ ...td, borderBottom: "none" }}>{fmtInr(totals.itc)}</td>
            <td style={{ ...td, borderBottom: "none" }}><UtilBar v={78} /></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/* --- right rail ----------------------------------------------------------- */

function ReportsLibrary() {
  return (
    <aside style={{
      width: 300, flex: "0 0 300px",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 16,
      alignSelf: "flex-start", position: "sticky", top: 24,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
          Reports library
        </div>
        <button style={{
          width: 24, height: 24, borderRadius: 6,
          border: "none", background: "transparent", cursor: "pointer",
          color: "var(--text-muted)", display: "grid", placeItems: "center",
        }}>
          <PlusIcon size={14} />
        </button>
      </div>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "8px 10px", borderRadius: 8,
        background: "var(--bg)", border: "1px solid var(--border)",
      }}>
        <SearchIcon size={14} />
        <input placeholder="Search reports"
          style={{
            flex: 1, border: "none", background: "transparent", outline: "none",
            fontSize: 12, color: "var(--text-primary)", minWidth: 0,
          }} />
      </div>
      {LIB.map(sec => (
        <div key={sec.group} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{
            fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em",
            color: "var(--text-muted)", fontWeight: 600,
          }}>
            {sec.group}
          </div>
          {sec.items.map((it: any, i) => (
            <button key={i} style={{
              display: "flex", alignItems: "flex-start", justifyContent: "space-between",
              gap: 8, padding: "10px 12px", borderRadius: 8, textAlign: "left",
              cursor: "pointer", border: "1px solid transparent",
              background: it.active ? "var(--accent-soft)" : "transparent",
              boxShadow: it.active ? "inset 3px 0 0 var(--accent)" : "none",
            }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{
                  fontSize: 12, fontWeight: 500,
                  color: it.active ? "var(--accent)" : "var(--text-primary)",
                  lineHeight: 1.3,
                }}>
                  {it.title}
                </div>
                <div style={{
                  fontSize: 11, color: "var(--text-muted)", marginTop: 2,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                  {it.meta}
                </div>
              </div>
              {it.spark && (
                <Sparkline data={it.spark} width={44} height={14}
                  stroke="var(--accent)" strokeWidth={1.5} fill />
              )}
            </button>
          ))}
        </div>
      ))}
    </aside>
  );
}

/* --- AI insights callout -------------------------------------------------- */

function AiInsights() {
  const bullets = [
    "Jul → Aug throughput dropped 26% while overdue count rose by 8 — this correlates with 2 clients migrating to QRMP.",
    "Kavya S. handles 90% of Composition-scheme clients but has the lowest on-time rate (93.5%) — consider rebalancing 20 clients to Neha Gupta.",
    "ITC recovered growth (+18% YoY) is outpacing filing throughput (+11%), driven by better 2B reconciliation matching after rule-pack v1.0.0.",
  ];
  return (
    <div style={{
      background: "var(--accent-panel-bg)",
      border: "1px solid var(--accent-panel-border)",
      borderRadius: 10, padding: 20,
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <SparklesIcon size={16} />
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--accent)" }}>
            AI insights
          </div>
        </div>
        <button style={{
          fontSize: 12, background: "transparent", border: "none", cursor: "pointer",
          color: "var(--accent)", fontWeight: 500,
        }}>
          Regenerate
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {bullets.map((b, i) => (
          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <div style={{
              width: 6, height: 6, borderRadius: 999,
              background: "var(--accent)", flex: "0 0 auto", marginTop: 8,
            }} />
            <div style={{ fontSize: 13, lineHeight: 1.55, color: "var(--text-primary)" }}>
              {b}
            </div>
          </div>
        ))}
      </div>
      <div style={{
        fontSize: 11, color: "var(--text-muted)", textAlign: "right",
        borderTop: "1px dashed var(--accent-panel-border)", paddingTop: 10,
      }}>
        Generated 2 min ago · Based on 1,847 filings · This is analysis, not advice
      </div>
    </div>
  );
}

/* --- page ---------------------------------------------------------------- */

export default function ReportsPage() {
  const [seg, setSeg] = useState<"type" | "status" | "owner">("type");
  const { cc, health, filings, timeliness, loading, error, reload } = useReportsData();
  const stacks = buildMonthlyStacks(filings, 12);
  const prevTotals = buildPrevTotals(filings, 12);
  const kpis = computeKpis(cc, health, stacks);
  const windowLabel = monthsWindowLabel();
  const segments: { key: typeof seg; label: string }[] = [
    { key: "type",   label: "By return type" },
    { key: "status", label: "By status" },
    { key: "owner",  label: "By owner" },
  ];
  const legend = [
    { label: "GSTR-1", color: "var(--accent)" },
    { label: "GSTR-3B", color: "var(--success)" },
    { label: "Other", color: "var(--text-secondary)" },
  ];
  return (
    <div style={{
      maxWidth: 1600, margin: "0 auto", padding: 24,
      display: "flex", gap: 16, alignItems: "flex-start",
    }}>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
        {error && <ErrorBanner message={`Could not load reports: ${error}`} onRetry={reload} />}
        {/* header card */}
        <div style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 24,
          display: "flex", flexDirection: "column", gap: 16,
        }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>
                Reports · Firm analytics · Filing performance
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <h1 style={{
                  fontSize: 24, fontWeight: 600, letterSpacing: "-0.01em",
                  color: "var(--text-primary)", margin: 0,
                }}>
                  Filing performance
                </h1>
                <div style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  padding: "3px 10px", borderRadius: 999,
                  border: "1px solid var(--border)",
                  fontSize: 12, color: "var(--text-secondary)", fontWeight: 500,
                }}>
                  <CalendarIcon size={12} /> {windowLabel}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "8px 12px", fontSize: 12, fontWeight: 500,
                color: "var(--text-secondary)", background: "transparent",
                border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer",
              }}>
                <DownloadIcon size={14} /> Export
              </button>
              <button style={{
                width: 32, height: 32, borderRadius: 8,
                border: "1px solid var(--border)", background: "transparent",
                cursor: "pointer", color: "var(--text-muted)",
                display: "grid", placeItems: "center",
              }}>
                <MoreHorizontalIcon size={14} />
              </button>
            </div>
          </div>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            gap: 12, flexWrap: "wrap",
          }}>
            <div style={{
              display: "inline-flex", border: "1px solid var(--border)",
              borderRadius: 8, overflow: "hidden", height: 32,
            }}>
              {segments.map((s, i) => (
                <button key={s.key}
                  onClick={() => setSeg(s.key)}
                  style={{
                    padding: "0 12px", fontSize: 12, fontWeight: 500,
                    border: "none", cursor: "pointer",
                    borderLeft: i === 0 ? "none" : "1px solid var(--border)",
                    background: seg === s.key ? "var(--accent-soft)" : "transparent",
                    color: seg === s.key ? "var(--accent)" : "var(--text-secondary)",
                  }}>
                  {s.label}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              {legend.map(l => (
                <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 2, background: l.color }} />
                  <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{l.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* KPI strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {kpis.map((k, i) => (
            <KpiCell
              key={i}
              label={k.label}
              value={loading && k.value === "—" ? "…" : k.value}
              delta={k.delta}
              deltaTone={k.deltaTone === "neutral" ? "accent" : k.deltaTone}
              spark={k.spark}
              sparkTone={k.sparkTone}
            />
          ))}
        </div>

        {/* filings by month */}
        <div style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 24, display: "flex", flexDirection: "column", gap: 20,
        }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
                Filings by month
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                Stacked by return type · dashed outline is prior 12-mo period
              </div>
            </div>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "4px 10px", borderRadius: 999,
              background: "var(--success-soft)", color: "var(--success)",
              fontSize: 12, fontWeight: 500,
            }}>
              <ArrowUpIcon size={12} /> +11.4% YoY
            </div>
          </div>
          <StackedBars stacks={stacks} prevTotals={prevTotals} />
        </div>

        {/* filing timeliness */}
        <div style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 10, padding: 24, display: "flex", flexDirection: "column", gap: 20,
        }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
                Filing timeliness
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                On-time % by return type over trailing 12 months
              </div>
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              {[
                { label: "GSTR-1", color: "var(--accent)" },
                { label: "GSTR-3B", color: "var(--success)" },
              ].map(l => (
                <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 10, height: 2, background: l.color, borderRadius: 2 }} />
                  <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{l.label}</div>
                </div>
              ))}
            </div>
          </div>
          <TimelinessChart data={timeliness} loading={loading} />
        </div>

        <TeamTable />
        <AiInsights />
      </div>
      <ReportsLibrary />
    </div>
  );
}
