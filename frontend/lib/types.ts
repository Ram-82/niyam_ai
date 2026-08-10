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
  blockers_ca: number;
  blockers_client: number;
  last_computed_at: string | null;
  filing_status: "draft" | "approved" | "filed" | null;
}

export interface CommandCenterSummary {
  total_rows: number;
  unfiled_count: number;
  filed_count: number;
  total_itc_at_risk_paise: number;
  high_risk_count: number;
  due_soon_count: number;
}

export interface CommandCenterResponse {
  period: string;
  rows: CommandCenterRow[];
  summary: CommandCenterSummary;
}

export interface ReconSummary {
  matched: {
    count: number;
    paise: number;
    // Stage-3 ITC split. Present on new pulls; the UI must show
    // ``paise_claimable`` in the ITC-total number and surface
    // ``paise_not_available`` as a separate callout (blocked-credit rows
    // reconcile but cannot be claimed).
    paise_claimable?: number;
    paise_not_available?: number;
    description?: string;
  };
  probable: {
    count: number;
    paise: number;
    paise_claimable?: number;
    paise_not_available?: number;
    description?: string;
  };
  supplier_default: {
    count: number;
    paise: number;
    with_near_misses?: number;
    top_suppliers?: Array<{ supplier_gstin: string; paise: number; count: number }>;
    description?: string;
  };
  missing_entry: { count: number; paise: number; description?: string };
  cdn?: { count: number; paise: number; description?: string };
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
    /** Set by POST /match-results/{id}/mark-near-miss-reviewed. Presence
     * unlocks the WhatsApp supplier_chase gate — do not treat as a mere
     * UI hint; the backend enforces the same check. */
    near_miss_reviewed_at?: string;
    /** Present when the CA has taken supplier chase action for this row.
     * Populated by the workspace client after a successful send so the
     * UI can badge the row without re-fetching. */
    last_chase_delivery_request_id?: string;
    /** Optional: supplier GSTIN copied off the register invoice for
     * the chase modal's "context" line. Populated by the backend when
     * available; can be inferred from the invoice on the frontend. */
    supplier_gstin?: string;
    /** Optional: register invoice number/date, used to populate the
     * chase message template. */
    register_invoice_number?: string;
    register_invoice_date?: string;
    register_total_paise?: number;
    /** B2B side details populated by list_matches JOIN on b2b_entry. */
    b2b_invoice_number?: string;
    b2b_invoice_date?: string;
    b2b_total_paise?: number;
    b2b_itc_available?: boolean;
    /** Set by POST /match-results/{id}/mark-reviewed. */
    reviewed_at?: string;
    reviewed_reason?: string;
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
  whatsapp_number?: string | null;
}


export interface GstinClientInfo {
  gstin_profile_id: string;
  gstin: string;
  client_id: string;
  trade_name: string;
  language: string;
  whatsapp_number: string | null;
}

export interface User {
  id: string;
  email: string;
  role: "admin" | "staff";
  is_active: boolean;
  totp_confirmed: boolean;
  last_login_at: string | null;
}

export interface InviteRow {
  id: string;
  email: string;
  role: "admin" | "staff";
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
}

export interface InviteCreated {
  invite_id: string;
  invite_token: string; // raw token — shown ONCE on creation
  expires_at: string;
}

export interface CalendarRow {
  gstin_profile_id: string;
  gstin: string;
  client_id: string;
  client_trade_name: string;
  scheme: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  due_date: string; // ISO YYYY-MM-DD
  days_out: number; // negative = overdue
  filing_status: "draft" | "approved" | "filed" | null;
  reminders_sent: number;
}

export interface CalendarResponse {
  today: string;
  horizon_days: number;
  lookback_days: number;
  rows: CalendarRow[];
}

export interface FirmSettings {
  name: string;
  plan: string;
  reminders_enabled: boolean;
}

export interface Me {
  id: string;
  email: string;
  firm_id: string;
  firm_name: string;
  role: "admin" | "staff";
  totp_confirmed: boolean;
  last_login_at: string | null;
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


// ---------------------------------------------------------------------------
// GSP (P2)
// ---------------------------------------------------------------------------


export type GspConnectionState =
  | "not_connected"
  | "connected"
  | "reconnect_needed";

export type GspRevokeReason =
  | "consent_revoked"     // Vendor pulled consent
  | "session_expired"     // TTL elapsed
  | "reconnect"           // Superseded by a subsequent connect
  | "user_disconnected";  // Manual disconnect

export interface GspBackfillItem {
  period: string;
  label: string;
}

export interface LatestGspAttempt {
  id: string;
  status: "running" | "succeeded" | "failed" | "retry_scheduled";
  error_kind: string | null;
  started_at: string;
  finished_at: string | null;
  next_retry_at: string | null;
}

export interface GspConnectionStatus {
  gstin_profile_id: string;
  gstin: string;
  // Session-only state. The panel derives the fourth "last_pull_failed"
  // UI state by blending this with ``latest_attempt`` — see
  // ``ConnectionsPanel::derivePanelState`` (P2.1 Stage E).
  state: GspConnectionState;
  reason: GspRevokeReason | null;
  session_expires_at: string | null;
  last_successful_pull_at: string | null;
  last_pull_period: string | null;
  sandbox_mode: boolean;
  monthly_call_count: number;
  backfill_offer: GspBackfillItem[];
  latest_attempt: LatestGspAttempt | null;
}

export type GspPullAttemptStatus =
  | "running"
  | "succeeded"
  | "failed"
  | "retry_scheduled";

export interface GspPullAttempt {
  id: string;
  gstin_profile_id: string;
  period: string;
  source: "manual" | "scheduled";
  status: GspPullAttemptStatus;
  attempt_count: number;
  error_kind: string | null;
  error_message: string | null;
  gstn_pull_id: string | null;
  started_at: string;
  finished_at: string | null;
  next_retry_at: string | null;
}


// ---------------------------------------------------------------------------
// Narrator (P2)
// ---------------------------------------------------------------------------


export type NarrationLanguage = "en" | "hi" | "kn" | "mr";

export interface NarrationOutput {
  narration_run_id: string;
  provider: string;
  model: string;
  language: NarrationLanguage;
  page1_health: string;
  page1_tax_position: string;
  page2_attention: string;
  page2_ask_your_ca: string;
}

export interface NarrationRunRow {
  id: string;
  gstin_profile_id: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  language: NarrationLanguage;
  provider: string;
  model: string;
  generated_at: string;
}


// ---------------------------------------------------------------------------
// WhatsApp delivery (P2)
// ---------------------------------------------------------------------------


export type DeliveryStatus =
  | "queued"
  | "sent"
  | "delivered"
  | "read"
  | "failed";

export type WhatsAppErrorKind =
  | "template_not_approved"
  | "invalid_number"
  | "rate_limited"
  | "meta_5xx"
  | "other";

export interface DeliveryAttemptRow {
  id: string;
  delivery_request_id: string;
  provider: string;
  status: DeliveryStatus;
  provider_message_id: string | null;
  error_kind: WhatsAppErrorKind | null;
  error_message: string | null;
  attempted_at: string;
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
}

export interface DeliveryRequestCreatedResponse {
  delivery_request_id: string;
}

export interface DeliverySendResponse {
  attempt_id: string;
  provider: string;
  provider_message_id: string;
  status: DeliveryStatus;
}


// ---------------------------------------------------------------------------
// Supplier contact directory (P2)
// ---------------------------------------------------------------------------


export interface SupplierContactRow {
  id: string;
  supplier_gstin: string;
  name: string;
  whatsapp_number: string | null;
  email: string | null;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_by: string | null;
  updated_at: string;
}


export interface ChasePreview {
  language: NarrationLanguage;
  template_name: string;
  body: string;
  supplier_name: string | null;
  supplier_gstin: string;
  firm_name: string;
}


// ---------------------------------------------------------------------------
// Filings (GSTR-1 / GSTR-3B draft JSON)
// ---------------------------------------------------------------------------


export type FilingStatus = "draft" | "approved" | "filed";


export interface FilingRow {
  id: string;
  gstin_profile_id: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  status: FilingStatus;
  rule_pack_version: string;
  generated_by: string | null;
  created_at: string;
  updated_at: string;
  payload: Record<string, unknown> | null;
}


// ---------------------------------------------------------------------------
// Audit log (firm activity feed)
// ---------------------------------------------------------------------------


export interface AuditRow {
  id: string;
  firm_id: string;
  user_id: string | null;
  user_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  diff: Record<string, unknown>;
  at: string;
}
