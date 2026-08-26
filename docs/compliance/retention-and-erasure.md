# Retention & Erasure — design

**Status:** DRAFT — mechanism-only pass. Retention *periods* and
statutory erasure *scope* are policy questions that require legal
counsel and CA sign-off. Every such question in this document is
marked `TODO-VERIFY-WITH-COUNSEL` or `TODO-VERIFY-WITH-CA`.

**Author:** Claude Code (P3 Phase 1 pass, 2026-08-19)
**Scope of this pass:** design the erasure mechanism and ship the
minimum plumbing (per-subject encryption key + erasure-request record)
so that when policy lands there is code to invoke. **No retention period
is defaulted; no automatic deletion is scheduled.**

---

## 1. Purpose

Niyam AI processes personal data on behalf of CA firms. Two independent
duties collide inside this repo and must be reconciled without weakening
either:

- The **audit log is immutable** by database trigger. Regulators and
  the platform's own defensibility both depend on that guarantee. See
  `audit_log`'s BEFORE UPDATE and BEFORE DELETE triggers in migration
  0001_initial (search for `niyam_forbid_mutation`).
- A **data-subject erasure obligation** may require that identifying
  information about a specific person no longer be reconstructable —
  including from an audit trail.

Row-level deletion in immutable tables is not an option. This document
argues for **crypto-shredding**: identifying data about a subject is
stored encrypted under a per-subject key; erasure destroys the key. The
ciphertext remains; nothing can reverse it.

---

## 2. Data inventory

Fields listed here are what a reasonable person would call "personal
data" in the Indian DPDPA sense. **The categorisation of each field as
"personal data" is a claim requiring counsel confirmation** —
`TODO-VERIFY-WITH-COUNSEL`.

Categorised by whose data it is, because the erasure duty differs:

### 2.1 CA firm staff (users of Niyam AI itself)

Data subject is the CA firm's employee — the human who logs into the
product.

| Table | Column(s) | Notes |
|-------|-----------|-------|
| `app_user` | `email`, `password_hash`, `totp_secret`, `last_login_at` | Login credentials + login history. |
| `user_invite` | `email` | Invitation records to future staff. |
| `password_reset` | `email` (via join), `token_hash` | Reset flow artefacts. |
| `audit_log` | `user_id` (FK), `diff` may embed email/name | User's own actions on the platform. |
| `legal_acceptance` | `user_id` (FK), `ip_address`, `user_agent` | IP + UA of the staff member who clicked "accept" on Terms/DPA. Both are personal data — IP identifies a device/location, UA fingerprints a browser install. Retained as evidence of who accepted what; erasure of that staff user must include zeroing these columns on their rows (per section 4.3, this is done by destroying the subject key that wraps them once we migrate them to encrypted-at-rest storage; ``legal_acceptance`` is APPEND-ONLY so raw row deletion is not on the table). |

### 2.2 The CA firm's clients (the businesses whose GST filings Niyam AI processes)

Data subject is the CA firm's client entity. Some fields (e.g.
`whatsapp_number`) are attached to a natural person contact at the client.

| Table | Column(s) | Notes |
|-------|-----------|-------|
| `client` | `trade_name`, `whatsapp_number` | Trade name may be a proprietor's own name. |
| `gstin_profile` | `gstin` | GSTIN is a business identifier but a proprietor's PAN is derivable from digits 3–12. |
| `invoice` | `invoice_number`, `counterparty_gstin`, `taxable_value_paise`, `total_paise`, ... | Detailed transaction records. |
| `b2b_entry` | `supplier_gstin`, `invoice_number`, `supplier_name` (if present) | Rows pulled from GSTN via 2B/1A. |
| `delivery_request` | `whatsapp_number_snapshot` | Snapshot of number at send time. |
| `ocr_extraction` | `raw_extraction` JSONB, `edited_extraction` JSONB | Full text of scanned invoices. |
| `narration_run` | narration text (JSONB) | Generated commentary embedding client names + amounts. |

### 2.3 Third-party natural persons (suppliers surfaced in 2B; contacts stored for reminders)

Data subject is a person who never signed up for Niyam AI but whose
information appears because a CA firm's client transacted with them.

| Table | Column(s) | Notes |
|-------|-----------|-------|
| `supplier_contact` | `supplier_gstin`, `whatsapp_number`, `email` | Explicitly persisted contact records for reminder chases. |
| `b2b_entry` | `supplier_gstin` etc. | Records from GSTN filings. |
| `reminder_log` | `recipient_email`, `recipient_whatsapp_number` | Delivery targets for reminder messages. |
| `ca_firm` | `admin_whatsapp_number` | Firm admin's own number for platform-side alerts. |

**Cross-references to audit trail.** The `audit_log.diff` JSONB blob
records "what was inserted / updated / deleted" for many operations and
may embed any of the above. It cannot be selectively rewritten.

### 2.4 Data NOT inventoried here as personal data

- Money amounts (paise integers), tax scheme labels, dates,
  reconciliation match outcomes — the transaction *shape* is business
  data of the client entity, not personal data of an identified
  natural person. `TODO-VERIFY-WITH-COUNSEL`: confirm this
  categorisation is correct under DPDPA 2023 as currently in force.

---

## 3. The design constraint

The audit-log triggers **must not be relaxed** to permit erasure.
Weakening them to satisfy one obligation would destroy the platform's
defensibility for every other purpose. Any design that requires
`ALTER TABLE audit_log ... DROP TRIGGER` is rejected here.

Therefore erasure means: **make the personal data unreadable while
leaving the row structurally intact**. The audit trail continues to
show *that* an action was taken, *when*, *by which user id*; the
identifying content of the diff becomes recoverable only with a key
that has been destroyed.

---

## 4. Proposed approach — crypto-shredding per subject

### 4.1 Subject key

Each data subject (a CA-firm client, a supplier appearing in 2B, a
CA-firm staff user) gets a per-subject symmetric encryption key stored
in a dedicated table:

```
subject_key(
  id UUID PK,
  firm_id UUID NOT NULL,               -- RLS scoped
  subject_kind TEXT NOT NULL,          -- 'client' | 'supplier' | 'app_user'
  subject_ref TEXT NOT NULL,           -- e.g. client_id or gstin or user_id
  key_material BYTEA NOT NULL,         -- symmetric key
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  destroyed_at TIMESTAMPTZ,            -- NULL until erased
  UNIQUE (firm_id, subject_kind, subject_ref)
)
```

RLS: firm-scoped. `subject_key` is NOT append-only — it needs
`destroyed_at` to be UPDATE-able. The row itself is retained after
destruction (so that "this subject was erased at time T" is auditable)
but `key_material` is overwritten with zeros.

### 4.2 What is written encrypted vs plaintext

**Not everything encrypted.** The design is targeted:

- **Encrypted at rest** (via the subject key): free-form text fields
  that would identify the subject to a reader — narration text,
  ocr_extraction raw JSON, supplier_contact.email /
  whatsapp_number, reminder_log recipient fields, audit_log.diff
  contents that embed subject text.
- **Not encrypted**: structural columns needed for RLS, joins,
  reconciliation, and rule-pack evaluation — `firm_id`, `client_id`,
  `gstin_profile_id`, `invoice_number`, monetary amounts, dates,
  reconciliation match buckets. These are *business* data about the
  transaction and are not the erasure target.

`TODO-VERIFY-WITH-COUNSEL`: this partitioning — encrypting free text
but retaining monetary/temporal/structural records — must be
confirmed as sufficient under DPDPA. If counsel decides that GSTIN
itself is personal data whose erasure is required, the design must
extend to tokenising GSTIN references in all read paths.

### 4.3 Erasure

A row is added to `erasure_request` (see 4.4). On execution, the
worker:

1. Overwrites `subject_key.key_material` with zeros using an owner
   engine (bypasses RLS).
2. Sets `subject_key.destroyed_at = now()`.
3. Records a row in `audit_log` (the *fact* of erasure is auditable).
4. Does not touch any encrypted ciphertext anywhere. The ciphertext
   is now unrecoverable because the only key was destroyed.

The `audit_log` row entry for erasure MUST NOT contain any
identifying information about the subject — only the internal
`subject_key.id`. `TODO-VERIFY-WITH-COUNSEL`: confirm this is
acceptable evidence for regulators.

### 4.4 Erasure request record

```
erasure_request(
  id UUID PK,
  firm_id UUID NOT NULL,
  subject_key_id UUID NOT NULL REFERENCES subject_key(id),
  requested_by UUID REFERENCES app_user(id),      -- who initiated
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'pending',         -- pending|executed|refused
  executed_at TIMESTAMPTZ,
  refusal_reason TEXT
)
```

Not append-only (needs status transitions). RLS scoped. Firms can
refuse an erasure request (e.g. active tax proceedings) but must
record why — `TODO-VERIFY-WITH-COUNSEL` for the acceptable refusal
categories under DPDPA.

### 4.5 Key wrapping

`subject_key.key_material` itself should be wrapped by a KEK held
outside the primary database (KMS, Vault, or `app.gsp.crypto`-style
env-provisioned key). Without wrapping, an attacker who exfiltrates
the DB has both the keys AND the ciphertext, defeating the design.

`TODO-VERIFY-WITH-OWNER`: choose KEK location (KMS candidate, Vault
candidate, env-derived candidate); the `app.gsp.crypto` module
already establishes an env-variable-based key convention that could
be reused.

---

## 5. Deliberately out of scope in this pass

- **Retention periods.** No table gets an automatic "delete after N
  years" job. Retention duration is a policy question that requires
  CA input (statutory records retention under GST/Income Tax) and
  counsel input (DPDPA proportionality). Recorded here as
  `TODO-VERIFY-WITH-CA` (GST record-keeping requirement, currently
  believed to be six years but assume it may have changed since
  training-data cutoff) and `TODO-VERIFY-WITH-COUNSEL` (DPDPA
  minimum-necessary-duration analysis).
- **Automatic erasure on account close.** Every erasure is
  explicitly requested and explicitly executed. No implicit
  deletion.
- **Notification obligations.** DPDPA sets notification duties on
  the data-fiduciary in certain cases (breach, refusal of an
  erasure request, etc.). This design does not implement notification
  flows. `TODO-VERIFY-WITH-COUNSEL`.
- **Backup handling.** Encrypted data in backups is still recoverable
  from a backup if the key was also backed up. The backup-retention
  interaction with crypto-shredding needs a separate design:
  `docs/ops/restore-drill.md` (Phase 1.5) is the natural home.
- **Encryption of ALL fields listed in section 2.** This pass ships
  the *mechanism* (subject key + erasure request table). The
  *migration of existing plaintext columns to ciphertext* is
  per-column work and is not part of P3 Phase 1. Each column
  migration will be its own change.

---

## 6. Implementation plan for this phase

Only the mechanism ships in P3 Phase 1:

1. Migration `0023_subject_key_and_erasure.py`:
   - `subject_key` table + RLS + firm-isolation policy (USING + WITH CHECK).
   - `erasure_request` table + RLS + firm-isolation policy.
   - Both tables get `GRANT SELECT, INSERT, UPDATE ON ... TO niyam_app`
     because both need mutability (subject_key for destruction,
     erasure_request for status transitions). Neither is append-only.
2. `app/erasure/keys.py`: helper to allocate and rotate a subject key.
   Key material generated with `os.urandom(32)`. Wrapping via
   `app.gsp.crypto` style envelope (KEK from env). `TODO-VERIFY-WITH-OWNER`
   on final KEK source.
3. `app/erasure/service.py`: `create_request(firm_id, subject_kind,
   subject_ref, requested_by)` and `execute(request_id)` — the latter
   is admin-only and gated behind a per-request review.
4. Tests:
   - subject_key generates a key, wraps it, unwraps it, round-trips
     an encrypt/decrypt.
   - after destroy: unwrap fails, `destroyed_at` set, `key_material`
     zeroed.
   - RLS: firm A cannot see firm B's subject_keys or erasure_requests.
   - erasure_request status transitions permitted (`pending`→
     `executed` and `pending`→`refused`); further transitions
     rejected.
5. **No** column migrations. **No** production erasure path enabled
   yet (endpoint is admin-only and marked with a startup assertion
   that the KEK is configured).

This is a *mechanism-only* deliverable. Executing a real erasure
against real personal-data columns is a follow-up per-column
project, which the owner + counsel must sequence.

---

## 7. Open questions requiring counsel or CA sign-off

Collected here so a single review can address them:

`TODO-VERIFY-WITH-COUNSEL`:
- What is the operative scope of "personal data" under DPDPA 2023 (as
  currently amended) for the fields in section 2? In particular:
  is a GSTIN alone personal data? Is a client trade name?
- Is crypto-shredding a lawful erasure implementation, or is
  regulator guidance that physical row deletion is required?
- Are refusals of erasure requests permitted, and if so, on what
  grounds (active tax proceedings? audit hold? contractual
  retention?)? What notification is owed to the requester?
- What breach/incident notification duties attach to a lost or
  disclosed subject key, given the design implication that key loss
  = effective erasure?
- Are the sub-processors listed on the current DPA page (AWS Mumbai,
  Anthropic US, Google Vertex asia-south1, WhatsApp, Postmark)
  correctly disclosed, and are the international-transfer safeguards
  in place under the current regime?

`TODO-VERIFY-WITH-CA`:
- What is the operative retention period for GST invoice records
  under the current statute and rules (belief at time of writing:
  six years from year-end, but assume this may have changed)?
- What is the operative retention period for return filings and
  reconciliation working papers?
- Are there record-holding duties under the Income Tax Act that
  extend or override the GST retention period?

`TODO-VERIFY-WITH-OWNER`:
- Where should the KEK live? Options: AWS KMS (matches existing
  hosting), HashiCorp Vault, `app.gsp.crypto`-style env-provisioned.
- Is a per-firm KEK acceptable, or is a single platform-level KEK
  the design? A per-firm KEK simplifies "close the firm's account"
  to a single-key destruction.

---

## 8. Non-goals (explicit)

To prevent scope creep:

- Not a policy document. Does not set retention durations.
- Not a rewrite of any existing column to be encrypted.
- Not a KEK selection. Ships with an env-provisioned placeholder
  and a startup assertion that fails loudly if the KEK is missing
  from production.
- Not a DPDPA compliance statement. The mechanism is a *precondition*
  for compliance, not compliance itself.
