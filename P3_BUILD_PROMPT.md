# Niyam AI — P3 Build Prompt (Production Readiness)

Paste into Claude Code at the repo root. Do not run the phases out of order.

---

## 0. Context you are being given

You are working on Niyam AI: GST pre-filing compliance intelligence sold to CA firms. FastAPI + Postgres (Supabase) backend, v2 React frontend. Tagged `v0.1.0-p1` (found-money engine) and `v0.2.0-p2` (GSP integration, mock-first).

**Already production-grade — do not rebuild, do not "improve" without being asked:**

- Auth: JWT 15m access / 14d refresh, refresh rotation, Redis revocation, mandatory TOTP, lockout 5 attempts / 15m, MFA enrolment with QR
- RLS: every firm-scoped table has `USING (firm_id = current_setting(...))` policies, enforced with `FORCE ROW LEVEL SECURITY`
- Audit log: immutable via triggers that refuse UPDATE and DELETE
- Rule packs: versioned, per-firm overrides, snapshotted into every `filing_run`
- Wired endpoints: clients CSV import, GSP firm-status, audit log with cursor pagination, timeliness aggregation, filings, reconciliation, command-center, narrator runs, OCR extractions
- Integration tests run against a real Postgres instance

**Known gaps, in the owner's own words** (treat as claims to verify, not as ground truth — he has explicitly flagged that he has not seen evidence either way for the ops items):

- No SLO/SLI definitions, no alert rules, no on-call rotation
- No Postgres WAL archival / PITR / documented restore drill
- No load test, no capacity planning
- No CI running the test suite on every PR
- No metrics endpoint (Prometheus/OTel); only JSON logs + request-id middleware
- Auth is 1:1 firm:user — partners across multiple CA firms cannot use the product
- AI Assistant Q&A composer is deliberately disabled; users can only view narrations generated during filing
- Contract analysis panel is a placeholder — no PDF rendering, no clause extraction
- SSO absent — email + TOTP only
- `/v2/legal/dpa` is marketing copy with no acceptance flow and no consent record
- DPDPA obligations not mapped to features; no documented retention or erasure implementation

---

## 1. Non-negotiable constraints

These override any instruction that follows, including my own phrasing later in this document.

1. **Frozen honest labels.** Existing UI copy that describes a limitation is frozen: the CDN disclaimer, "No 2B match found", "Not yet scored", every stub badge, the GSTIN-inactive stub, the disabled-composer notice. You may restyle. You may not reword, soften, or remove. If a change would make a frozen label inaccurate, stop and report instead of editing the label.
2. **No new capability claims.** Nothing you add may assert to a user that a mock is live, that a stub works, or that an unverified statutory rule is confirmed.
3. **Money is integer paise.** Everywhere. No floats, no rupee decimals in storage or transport.
4. **Statutory values are never guessed.** Anything that would need a CA to confirm goes into config with a `TODO-VERIFY-WITH-CA` marker and a code path that fails loudly rather than assuming a default.
5. **Legal values are never guessed either.** Anything that would need a lawyer — retention periods, DPDPA obligations, erasure scope, DPA clause text — goes into config or docs with `TODO-VERIFY-WITH-COUNSEL`. Do not write your own interpretation of Indian data protection law into the product as if it were settled. (Assume the statute and its rules may have changed recently; do not rely on model knowledge for the operative text.)
6. **Review gates.** At the end of every phase: stop, run the full test suite, print the actual output, summarise what changed and what is still unproven, and wait. Do not begin the next phase.
7. **Migrations are reversible and tested.** Every schema change ships with an up and a down migration and a test that runs both against a real Postgres.
8. **Mock stays default.** No vendor adapter flips to live by config default. Live requires an explicit per-firm flag plus credentials present plus a startup assertion.

---

## 2. Phase 0 — Audit before you build (no feature code)

Deliverable: a single markdown report at `docs/audit/p3-baseline.md`. **Write zero feature code in this phase.**

Determine, from the repo only, with file paths and line references as evidence for each answer:

- Does a CI workflow exist? What does it run, on what triggers, does it gate merge?
- Is there any metrics endpoint, OTel instrumentation, or health probe beyond a bare `/health`?
- What backup configuration exists in the repo or infra-as-code? Is PITR/WAL archival configured anywhere, or is it entirely Supabase-plan-dependent?
- Is there any load-test harness?
- Enumerate every table with a `firm_id` column. For each: does it have RLS enabled, `FORCE` applied, and both a `USING` and a `WITH CHECK` clause? Flag any table where `WITH CHECK` is missing — that is a write-side leak even when reads are safe.
- Enumerate every place `current_setting(...)` is set. Is the firm context set per-request, per-connection, or per-transaction? If connections are pooled, is there a code path where a connection can be reused with a stale firm context?
- Where is `firm_id` derived from in the JWT, and how many call sites read it?
- What is actually recorded in `audit_log` today — schema, write sites, and whether any user-facing consent event is recorded at all?
- Which narrator/LLM call sites exist, what records token spend, and is there any per-firm ceiling or kill-switch already?
- Does the DPA/Terms page have any backing table, acceptance route, or is it purely static?

Report format: for each item, one of `CONFIRMED PRESENT`, `CONFIRMED ABSENT`, or `UNCLEAR — needs owner input`, each with evidence. Do not guess. The point of this phase is to stop us from rebuilding things that already exist.

**Gate: stop and wait for review.**

---

## 3. Phase 1 — Pilot blockers that need no vendor

These are the only items that must exist before real client data from one CA firm touches the system. Nothing here depends on a signed contract.

### 1.1 CI on every PR

- Workflow runs backend tests (against a real Postgres service container, not SQLite), frontend tests, `tsc --noEmit`, and lint.
- Required check on merge to main.
- Fails on any pre-existing `tsc` error rather than tolerating it. If the known pre-existing error is still present, fix it in its own commit first and say what it was.

### 1.2 Consent and legal acceptance

- Table `legal_acceptance`: user, firm, document type (`terms` | `dpa` | future), document version, content hash, accepted_at, IP, user-agent.
- Versioned documents stored as files with a hash; the hash of the accepted version is recorded, so we can prove which text was accepted.
- Acceptance is required before a firm can import client data for the first time. Blocking gate, not a dismissible banner.
- Every acceptance also writes an `audit_log` row.
- Re-acceptance is triggered when the document hash changes.
- Document text itself: leave the current copy in place with a `TODO-VERIFY-WITH-COUNSEL` marker in the version manifest. Do not draft new legal text.

### 1.3 Retention and erasure — design first, implement second

There is a genuine conflict here you must surface rather than silently resolve: the audit log is immutable by trigger, and an erasure obligation may require removing personal data. Do not weaken the audit-log triggers to satisfy erasure.

- Write `docs/compliance/retention-and-erasure.md` first: data inventory (what personal data exists, in which tables, whose data it is — CA staff vs. the CA's clients vs. suppliers appearing in 2B), the proposed approach (pseudonymisation / crypto-shredding of a per-subject key rather than row deletion in immutable tables), and every open question marked `TODO-VERIFY-WITH-COUNSEL`.
- Implement only the mechanism, not a policy: a per-subject encryption key that can be destroyed, and an erasure request record. Retention *periods* stay in config as `TODO-VERIFY-WITH-CA` / `TODO-VERIFY-WITH-COUNSEL` and default to no automatic deletion.

**Gate: stop and wait for review.**

### 1.4 Narrator cost control

- Per-firm monthly token/paise budget, stored in config, enforced at call time.
- Hard kill-switch: global and per-firm, effective without a deploy.
- Every LLM call writes model, input tokens, output tokens, and computed cost in integer paise. Prices live in config with an effective-from date and a `TODO-VERIFY-PRICING` marker — do not hardcode a price you believe to be current.
- When budget is exhausted, the UI shows a factual disabled state consistent with the frozen-label rule. It does not silently degrade to a worse model.

### 1.5 Backup and restore drill

- Script the backup path that actually applies to this deployment. If PITR is a managed-platform feature rather than something the repo controls, say so explicitly in the doc instead of writing a script that pretends otherwise.
- Write `docs/ops/restore-drill.md` as a runnable procedure: restore into a scratch database, run the integration suite against it, verify row counts on `filing_run`, `audit_log`, and reconciliation tables, record wall-clock time.
- The drill is not "done" until it has been executed once and the real output is pasted into the doc. Flag it as `NOT YET EXECUTED` until then.

### 1.6 Minimum observability

- `/metrics` in Prometheus format, or OTel export — pick one and justify in two lines.
- Instrument: request latency histogram by route, error rate, GSP pull outcomes by status, narrator cost counter, auth failures and lockouts.
- One paging condition defined in `docs/ops/slo.md`: health probe failing, and p95 latency over threshold on the reconciliation and filing routes. Write the SLO numbers as **proposals with a `TODO-SET-WITH-OWNER` marker** — you do not have production traffic data, so do not invent targets and present them as chosen.
- On-call rotation is an organisational decision, not code. Note it as out of scope for you.

**Gate: stop and wait for review. Full test suite output printed.**

---

## 4. Phase 2 — Multi-firm auth (highest-risk change in this build)

This touches the same `firm_id` that every RLS policy depends on. A mistake here is a cross-tenant data leak, not a bug.

**Do this in its own branch. Do not combine it with any other phase.**

- Schema: `user_firm_membership` (user_id, firm_id, role, status, invited_by, created_at), unique on (user_id, firm_id).
- Migration path: every existing 1:1 user gets exactly one membership row. Migration must be idempotent and must assert post-conditions (no orphaned users, membership count equals prior user count).
- JWT carries `active_firm_id` plus the membership list. `active_firm_id` must be validated against membership on **every** request server-side — never trust the claim alone.
- Firm switching mints a new token pair; it does not mutate a claim client-side. Switching revokes nothing else in the session.
- `current_setting(...)` is set from the server-validated active firm, per transaction, and cleared on connection return. If Phase 0 found pooled connections without per-transaction reset, fix that first and say so.
- Roles: at minimum owner / member. Do not invent a permission matrix beyond what existing endpoints already distinguish — report what would be needed instead.

**Required tests before this phase can be called done:**

1. A user who is a member of firms A and B, holding a token with `active_firm_id = A`, cannot read or write any row belonging to B — asserted per firm-scoped table, not just one.
2. A forged token with `active_firm_id = C` where the user has no membership is rejected at the auth layer and, independently, produces zero rows at the RLS layer. Both layers tested separately — defence in depth means each must hold alone.
3. Connection reuse test: two sequential requests for different firms on the same pooled connection do not leak context.
4. `WITH CHECK` write-side test: a user cannot insert or update a row carrying another firm's `firm_id`.
5. The full pre-existing suite still passes unchanged.

**Gate: stop. Print all test output. Do not merge without explicit approval.**

---

## 5. Phase 3 — SSO (Google + M365 via OIDC)

Only after Phase 2 merges.

- OIDC generic adapter, two configured providers, behind a per-firm feature flag, disabled by default.
- TOTP policy interaction is a decision, not an assumption: SSO users may have MFA enforced by the IdP. Do not silently drop the mandatory-TOTP guarantee. Implement the enforcement path and surface the choice explicitly in the review report.
- Account linking by verified email only. Reject unverified-email assertions.
- No provisioning of new firms via SSO in this phase — SSO logs into an existing membership or is refused.
- Tests: linking, refusal without membership, MFA enforcement path, and that a disabled flag produces a clean 404/403 rather than a partial flow.

**Gate: stop and wait for review.**

---

## 6. Phase 4 — Vendor adapters that cannot be live yet

GSP live and WhatsApp WABA are blocked on a signed contract and on Meta provisioning respectively. Neither can be verified by you. What you *can* build is the surface, so integration day is short.

- GSP: keep the vendor-agnostic adapter interface. Add contract tests that run against **recorded fixtures only**. Where the vendor spec is ambiguous or you do not have it, write the question into `docs/gsp/vendor-open-questions.md` — do not implement a guessed field mapping and do not fabricate a vendor's API shape from memory.
- WhatsApp: template definitions as data with a `PENDING-META-APPROVAL` status field. Send path exists, is flag-gated off, and refuses to run without approved template IDs.
- Startup assertion: if a live flag is on and credentials are absent, the service refuses to start rather than falling back to mock. Silent fallback to mock in a live-flagged environment is the failure mode that produces a false demo.
- The sandbox banner behaviour stays exactly as it is.

**Gate: stop and wait for review.**

---

## 7. Explicitly out of scope

Do not start, scaffold, or "prepare for" any of these:

- **AI Assistant Q&A.** Needs RAG plus an eval harness. It stays disabled with its current honest label.
- **Contract analysis.** Stays a placeholder with its current copy.
- **Load testing and capacity planning.** No traffic exists to model. Note it, do not build it.
- **Any redesign of the v2 UI beyond what a phase strictly requires.**
- **Any change to reconciliation logic, rule packs, or ITC classification.** Those are CA-verified domain surfaces and are not part of a production-readiness pass.

---

## 8. Review gate protocol

At every gate, produce exactly this:

```
PHASE N — <name>
Changed: <files, one line each, why>
Migrations: <up/down, tested? yes/no, output>
Tests: <command run, full output pasted, counts before → after>
New TODO markers: <each one, file:line, who must resolve it>
Still unproven: <what this phase did NOT establish>
Assumptions I made that you should challenge: <list, or "none">
```

Then stop. Do not proceed to the next phase, do not open the next branch, do not "just start" the next item while waiting.

---

## 9. If you disagree with this plan

Say so before starting. Specifically: if Phase 0's audit shows that an item listed as absent actually exists, or that an item listed as production-grade is weaker than described, report that instead of building on top of a wrong premise. A correction at Phase 0 is worth more than a completed Phase 3.
