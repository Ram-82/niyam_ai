import { describe, it, expect } from "vitest";
import { summarizeRows } from "./summarize-command-center";
import type { CommandCenterRow } from "./types";


function row(over: Partial<CommandCenterRow>): CommandCenterRow {
  return {
    client_id: "c1",
    client_name: "C1",
    gstin_profile_id: "g1",
    gstin: "29AAAAA0000A1ZY",
    scheme: "regular",
    return_type: "GSTR1",
    period: "202606",
    score: 62,
    days_to_due_date: 5,
    itc_at_risk_paise: 4_300_000,   // ₹43,000
    blockers_count: 0,
    blockers_ca: 0,
    blockers_client: 0,
    last_computed_at: null,
    ...over,
  };
}


describe("summarizeRows — aggregation bases", () => {
  it("dedup: two return-type rows for the same (gstin, period) → ITC counted once", () => {
    const s = summarizeRows([
      row({ return_type: "GSTR1", days_to_due_date: 5 }),
      row({ return_type: "GSTR3B", days_to_due_date: 14 }),
    ]);
    expect(s.totalItcAtRiskPaise).toBe(4_300_000); // NOT 8_600_000
    expect(s.totalReturns).toBe(2);                // rows stay row-based
  });

  it("dedup: two gstin_profiles → ITC summed across distinct pools", () => {
    const s = summarizeRows([
      row({ gstin_profile_id: "g1", itc_at_risk_paise: 4_300_000 }),
      row({ gstin_profile_id: "g2", itc_at_risk_paise: 1_200_000 }),
    ]);
    expect(s.totalItcAtRiskPaise).toBe(5_500_000);
  });

  it("dedup: same gstin, different period → separate recon pools", () => {
    const s = summarizeRows([
      row({ period: "202605", itc_at_risk_paise: 4_300_000 }),
      row({ period: "202606", itc_at_risk_paise: 2_000_000 }),
    ]);
    expect(s.totalItcAtRiskPaise).toBe(6_300_000);
  });

  it("avgScore is null when no row has a score", () => {
    const s = summarizeRows([row({ score: null }), row({ score: null })]);
    expect(s.avgScore).toBe(null);
  });

  it("avgScore is mean of non-null scores (rounded)", () => {
    const s = summarizeRows([row({ score: 60 }), row({ score: 71 }), row({ score: null })]);
    expect(s.avgScore).toBe(66);      // (60 + 71) / 2 = 65.5 → 66
  });

  it("overdueReturns is row-based (each return_type has its own deadline)", () => {
    const s = summarizeRows([
      row({ return_type: "GSTR1", days_to_due_date: -2 }),   // overdue
      row({ return_type: "GSTR3B", days_to_due_date: 7 }),   // not overdue
    ]);
    expect(s.overdueReturns).toBe(1);
  });

  it("empty input", () => {
    const s = summarizeRows([]);
    expect(s).toEqual({
      totalReturns: 0,
      avgScore: null,
      totalItcAtRiskPaise: 0,
      overdueReturns: 0,
    });
  });
});
