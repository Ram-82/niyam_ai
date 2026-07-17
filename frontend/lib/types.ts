/** API response types (mirror app/api/*.py Pydantic models). */

export interface Blocker {
  code: string;
  description: string;
  owner: "ca" | "client";
  paise_impact: number;  // integer paise — pass through formatPaise before display
}

export interface CommandCenterRow {
  client_id: string;
  client_name: string;
  gstin_profile_id: string;
  gstin: string;
  scheme: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  score: number | null;               // null == "Not yet scored" (criterion #3)
  days_to_due_date: number | null;
  itc_at_risk_paise: number;
  blockers_count: number;
  last_computed_at: string | null;
}

export interface CommandCenterResponse {
  period: string;
  rows: CommandCenterRow[];
}

export interface ReconSummary {
  matched: { count: number; paise: number; description?: string };
  probable: { count: number; paise: number; description?: string };
  supplier_default: {
    count: number;
    paise: number;
    with_near_misses?: number;
    top_suppliers?: Array<{ supplier_gstin: string; paise: number; count: number }>;
    description?: string;
  };
  missing_entry: { count: number; paise: number; description?: string };
  disclaimer: string;
}

export interface ReconResponse {
  run_id: string | null;
  period: string;
  status: string | null;
  summary: Partial<ReconSummary>;
  rule_pack_version: string | null;
  finished_at: string | null;
}

export interface MatchResult {
  id: string;
  bucket: "matched" | "probable" | "supplier_default" | "missing_entry";
  confidence: number;
  invoice_id: string | null;
  b2b_entry_id: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
  rejected: boolean;
  context: {
    near_misses?: Array<{
      b2b_entry_id: string;
      supplier_gstin: string;
      invoice_number: string;
      invoice_date: string;
      total_paise: number;
      similarity: number;
    }>;
  };
}

export interface ReadinessResponse {
  snapshot_id: string | null;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  score: number | null;
  blockers: Blocker[];
  arithmetic: {
    components?: Array<{
      name: string;
      value: number;
      raw_weight: number;
      normalized_weight: number;
      weighted_contribution: number;
    }>;
    weighted_sum?: number;
    final_score?: number;
    rule_pack_version?: string;
    period?: string;
    return_type?: string;
    computed_for_date?: string;
    days_to_due_date?: number;
  };
  rule_pack_version: string | null;
  computed_at: string | null;
}

export interface Flag {
  id: string;
  invoice_id: string;
  rule_code: string;
  severity: "error" | "warning";
  message: string;
  resolved: boolean;
  rule_pack_version: string;
}

export interface Client {
  id: string;
  trade_name: string;
  language: string;
}

export interface User {
  id: string;
  email: string;
  role: "admin" | "staff";
  is_active: boolean;
  totp_confirmed: boolean;
}

/** Login response shape depends on TOTP enrolment status. */
export type LoginResponse =
  | {
      access_token: string;
      refresh_token: string;
      token_type: "bearer";
      expires_in: number;
    }
  | {
      totp_setup_token: string;
      expires_in: number;
    };
