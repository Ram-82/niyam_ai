# Niyam AI — P1 MVP

GST pre-filing intelligence for CA firms. P1 ships the **found-money engine**: purchase-register import, GSTR-2B import, deterministic validation, reconciliation with a 4-bucket ITC summary, and a filing-readiness score — surfaced in a Next.js CA dashboard.

> Positioning: **Niyam prepares and flags. The CA approves and advises.** The platform never files on its own judgment.

---

## Release notes — v0.1.0-p1

**What P1 does (all shipped, all tested):**

- Multi-tenant Postgres 15+ with Row-Level Security on every tenant table. `firm_id` denormalized onto every table for cheap policies. FastAPI connects as a NOBYPASSRLS app role.
- Auth: email + password + mandatory TOTP 2FA, JWT access/refresh with rotation, Redis-backed jti revocation, 5-fail/15-min lockout, admin invite flow (SHA-256 hashed tokens).
- Import pipeline (CSV/XLSX purchase and sales + GSTR-2B JSON) → RQ jobs → canonical normalization + content-hash dedup. Rejected rows are downloadable as CSV.
- Deterministic validation engine (R001–R008) reading every tolerance/slab/rate from a versioned `rule_pack` payload — no hardcoded statutory constants.
- Reconciliation engine: three-pass (exact → fuzzy → residuals) with closest-amount pairing in same-key groups. Every `supplier_default` residual is enriched with same-supplier near-misses, persisted on `match_result.context`.
- Readiness scoring engine: five weighted components, full arithmetic breakdown persisted to `readiness_snapshot.arithmetic` (append-only history). Blockers array carries `paise_impact` sourced from the reconciliation summary — the command-center sort key.
- Dashboard API (command center, workspace tabs, engine triggers, admin), every mutation writes to `audit_log`.
- Next.js dashboard: login+TOTP, command center (sorted by score × deadline), 3-tab workspace, imports, firm settings. BigInt-based money formatter, Indian digit grouping, unit-tested past ₹9 crore.
- Playwright E2E smoke covering login → command center → workspace → confirm probable → audit trail.
- `docker compose run --rm backend python -m scripts.seed_demo` produces the "₹43,000 ITC at risk from 6 suppliers" story on first load (mid-60s readiness score, exact ₹ arithmetic, both near-miss states visible, live-confirmable probables).

**What is stubbed for P2 (each has a clean contract at `backend/app/stubs/`):**

- GSP API — live GSTR-2B pulls and GSTIN status checks.
- LLM narrator — vernacular 2-pager prose. Hard rule preserved: the narrator never invents a number.
- WhatsApp Business — CA-approved report delivery under the firm's white-label brand.

Also deferred (no stub file — pure scope boundary): OCR, MSME mobile app, notice assistant, advisory nudge engine, Tally XML bridge.

**Known limitations shipped intentionally in P1 — read before demoing:**

- **R006 tax-arithmetic** — checks whether tax amounts match `taxable × rate` for one of the configured rates. It does NOT check that the invoice's declared rate matches the HSN master (P1 CSV has no rate column). A "wrong rate for HSN" error is P2.
- **CDN handling** — the schema carries `b2b_entry.note_type` but reconciliation and scoring do NOT net credit/debit notes against matched ITC. Every ITC figure in the UI, API, and CSV exports is labelled "Before credit/debit note adjustments." Do not remove this label until CDN is wired end-to-end.
- **Engine triggers are synchronous** — `POST /engines/{validate,reconcile,score}` runs inline. Fine at P1 volumes (~1000 invoices/GSTIN/period, subsecond); wrapping in `queue.enqueue` is a one-line change when profiling demands it.
- **Auth tokens in localStorage** — P1 dev/demo. Production hardening is httpOnly + SameSite=Strict cookies plus a lightweight anti-CSRF header.
- **"Inactive supplier" alert** — P1 uses R002 (checksum failure) as the stand-in. The true live-status check requires GSP integration (`app/stubs/gsp_api.py::check_gstin_status`).
- **Supplier risk window** — P1 counts a supplier as "risky" only if they appear in the CURRENT period's `supplier_default` bucket. The trailing-window definition is in the Domain-verification list.

**Dev-only secrets in the repo (all placeholders, none real):**

- `niyam:niyam@` Postgres credentials in `.env.example`, `docker-compose.yml`, `backend/alembic.ini`, `backend/app/config.py` defaults, and `frontend/e2e/*.ts` — all intentional dev defaults, all overridable via env.
- `JWT_SECRET=change-me-in-real-env` — explicitly labelled placeholder in `.env.example` and `config.py`.
- `DemoPassword-2026-Correct` / `JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP` — the demo firm's admin credentials in `backend/scripts/seed_demo.py`. Non-sensitive: they exist only after you run the demo seed against a demo DB.

Before deploying to any environment with real data: set `JWT_SECRET`, `DATABASE_URL`, `APP_DATABASE_URL`, `REDIS_URL`, and `NIYAM_CORS_ORIGINS` via env; do NOT run `seed_demo`.

**Domain verification needed** — see the numbered list below (§ "Domain verification needed"). Every item is a rule-pack knob today; every answer is one `INSERT INTO rule_pack (…, active) … + UPDATE`-toggle away. Bring the whole list to the first CA validation meeting.

---

## Status

* **Step 1** ✅ Repo skeleton + Alembic initial migration.
* **Step 2** ✅ SQLAlchemy models + firm-scoped session helper + RLS isolation tests.
* **Step 3** ✅ Auth: email+password + TOTP 2FA (mandatory) + JWT access/refresh + Redis-backed lockout (5 fails / 15 min) + Redis-backed jti revocation + admin invite flow (SHA-256 hashed tokens).
* **Step 4** ✅ Import pipeline: CSV/XLSX purchase & sales register uploads + GSTR-2B JSON uploads → **RQ jobs** on the `imports` queue → canonical normalization + content-hash dedup + b2b_entry insertion. Uploads land on a shared docker volume (`niyam_uploads → /data/uploads`) so the API and worker containers share files. Migration `0003_import_job.py` adds the `import_job` table with RLS. Rejected rows are stored inline (JSONB, capped at 10k) and materialized to CSV via `GET /imports/{id}/errors.csv`.
* **Step 5** ✅ Validation rule engine: 8 pure-function rules (R001–R008) reading tolerances/slabs/rates from the active `rule_pack` payload — no hardcoded statutory constants. Migration `0004_seed_rule_pack.py` seeds v1.0.0 (active). GSTIN checksum follows the CBIC mod-36 specification. `validate_period(firm_id, gstin_profile_id, period)` orchestrates: loads invoices, precomputes duplicate-key counts, runs the pipeline, upserts `validation_flag` rows (idempotent, replaces unresolved-per-version).
* **Step 6** ✅ Reconciliation engine — the "found money" demo. Three-pass algorithm (exact → fuzzy → residuals) over purchase register vs GSTR-2B. Pass 1 pairs by closest amount within same-key groups (not first-in-wins). Fuzzy scoring is a weighted `(number_similarity, date_closeness, amount_closeness)` with all thresholds/tolerances in the rule pack. Every `supplier_default` residual is enriched with same-supplier `near_misses` (persisted in `match_result.context` via migration 0005) so the CA sees "we found this similar unmatched 2B" before drafting a chase. Summary carries non-accusatory copy: "no 2B match found — could be register-side error, timing gap, or supplier default; review near_misses first."
* **Step 7** ✅ Readiness scoring — deterministic weighted 5-component score (validation pass rate, reconciliation match rate by *value*, data completeness vs trailing 3-month, supplier risk, days-to-due). Weights + due dates + curve params from rule pack. Full arithmetic breakdown persisted to `readiness_snapshot.arithmetic` so the dashboard's "click to see math" is a data pull. Blockers array pulls `paise_impact` from the reconciliation summary wherever computable (supplier_default totals, per-supplier at-risk, probable pending review, missing entries) — sort key for the command center. `readiness_snapshot` is append-only; every scoring run is a new immutable row.
* **Step 8** ✅ Dashboard API endpoints + `audit_log` on every mutation. See endpoint map below. In P1 the validate/reconcile/score triggers run synchronously (fast at P1 volumes ~1000 invoices/GSTIN/period); wrapping in `queue.enqueue` is a one-line change if profiling later demands it.
* **Step 9** ✅ Next.js dashboard — login+TOTP, command center, workspace (invoices/reconciliation/returns tabs), imports, settings. All eight acceptance criteria are enforced by shared components (see `frontend/components/atoms.tsx`) — money via `formatPaise()` with BigInt (unit-tested past 2^53 paise), CDN disclaimer on every ITC render, NULL score as "Not yet scored", persisted arithmetic JSONB in the drawer, blockers with owner+paise, softened `supplier_default` copy + `NearMissReview` gate. Playwright smoke at `frontend/e2e/smoke.spec.ts` (login → command center → workspace → confirm → audit trail).
* **Step 10** ✅ Demo seed + P2 stub interfaces + polished README. `scripts/seed_demo.py` produces the "₹43,000 at risk from 6 suppliers" story on first load — mid-60s readiness, exact ₹ arithmetic (sum of supplier_default rows = ₹43,000 to the paise), realistic blocker mix, two probables to confirm live. Idempotent: one command resets between meetings. P2 stub interfaces documented at `app/stubs/{gsp_api,llm_narrator,whatsapp}.py`.

---

## The demo — one command

Reset to the "₹43,000 at risk from 6 suppliers" state between meetings:

```bash
# Assumes docker compose up -d postgres redis is running.
docker compose run --rm backend python -m scripts.seed_demo
# Or with a fixed 'today' for reproducible score across the calendar:
docker compose run --rm backend python -m scripts.seed_demo --today 2026-07-05
```

Then open the dashboard:

```bash
docker compose up -d api worker frontend
open http://localhost:3000/login
```

Sign in with the credentials printed at the end of the seed script. The demo is deliberately targeted:

| What the CA sees on first load | Number |
|---|---|
| Readiness score (GSTR1) | ~65/100 (mid-60s) |
| Matched ITC (this period) | ₹2,50,000 |
| Probable — awaiting review | ₹1,50,000 (2 rows) |
| **Supplier_default — ITC at risk** | **₹43,000 across 6 suppliers** |
| — of which have same-supplier near-misses to review first | 2 |
| — of which are ungated ("no candidate found") | 4 |
| Missing register entry (in 2B, unrecorded) | ₹1,20,000 |
| Validation errors / warnings | 5 / 4 |

The supplier_default rows sum to **exactly ₹43,000** (₹18k + ₹8.5k + ₹5k + ₹4.5k + ₹4k + ₹3k) — a CA will do that arithmetic in their head at the demo. Every ITC figure on screen carries "**Before credit/debit note adjustments**".

**One of the supplier_default rows uses R002 (malformed GSTIN checksum) as the P1 stand-in for a "supplier appears inactive/cancelled" alert.** The live GSTN status check is P2 (see `app/stubs/gsp_api.py`). Frame it that way in the demo — the flag is real, the underlying live-status feed is what changes in P2.

### API endpoint map (step 8)

**Command center**
- `GET /command-center?period=YYYYMM` — one row per (client × GSTIN × return_type); score, days_to_due, itc_at_risk_paise, blockers_count; NULLs surface first, then score ASC, then days_to_due ASC. Staff sees only assigned clients.

**Clients** (admin-only mutations)
- `GET /clients`, `POST /clients`, `POST /clients/{id}/gstins`

**Workspace**
- `GET /gstins/{id}/invoices?period=` — invoices tab.
- `GET /gstins/{id}/flags?period=` — flags list.
- `POST /flags/{id}/resolve` — mark resolved (audited).
- `GET /gstins/{id}/reconciliation?period=` — recon tab summary + top suppliers.
- `GET /reconciliation-runs/{id}/matches?bucket=` — per-bucket match list; `context.near_misses` present on supplier_default rows.
- `POST /match-results/{id}/confirm` / `/reject` — probable disposition (audited).
- `GET /gstins/{id}/readiness?return_type=&period=` — returns tab: score + blockers + full arithmetic breakdown.

**Engine triggers** (audited)
- `POST /engines/validate` `{gstin_profile_id, period}`
- `POST /engines/reconcile` `{gstin_profile_id, period}`
- `POST /engines/score` `{gstin_profile_id, return_type, period}`

**Admin** (admin-only, audited)
- `GET /users`, `POST /assignments` `{user_id, client_id}`, `DELETE /assignments/{user_id}/{client_id}`

### Audit convention

Every mutation calls `app.auth.audit.record(...)` with `metadata={"before": {...}, "after": {...}}` for updates or `metadata={"after": {...}}` for creates. Action strings: `flag.resolved`, `match.confirmed`, `match.rejected`, `client.created`, `gstin.added`, `assignment.granted`, `assignment.revoked`, `validation.triggered`, `reconciliation.triggered`, `score.triggered`.

### Adding a validation rule

1. Add the pure function to `app/engines/validation/rules.py` matching `(invoice, ctx) -> Optional[Flag]`. Read tolerances from `ctx.rule_pack_payload['validation'][...]`.
2. Register it in the `RULES` tuple in `pipeline.py`.
3. Add parameters to the next rule_pack version under `validation.r00N_*`.
4. Add a test file (or a section in `test_validation_rules.py`).
5. Ship the new rule pack: `INSERT INTO rule_pack (version, payload, active) VALUES ('1.1.0', '{...}', FALSE); UPDATE rule_pack SET active=FALSE WHERE version='1.0.0'; UPDATE rule_pack SET active=TRUE WHERE version='1.1.0';`. The `rule_pack_single_active` partial unique index enforces mutual exclusion.

### Tally bridge (P1 pragmatic simplification)

The prompt calls for "CSV/Excel import that mirrors Tally export format." Real Tally exports are XML and vary by version. P1 defines a documented CSV/XLSX column contract (`invoice_number, invoice_date, counterparty_gstin, taxable_value, cgst, sgst, igst, total, hsn_sac`); users transform their Tally export to this shape client-side. A dedicated "Tally XML bridge" utility is P2 scope.

### Auth flow

1. `POST /auth/register` — accept an invite token + set password (creates unconfirmed-TOTP user).
2. `POST /auth/login` with `{email, password}` — returns `{totp_setup_token, expires_in}` if TOTP not yet enrolled, else expects `totp_code` too.
3. `POST /auth/totp/setup` (Bearer: totp_setup token) — returns `{provisioning_uri, secret}` (idempotent while unconfirmed).
4. `POST /auth/totp/verify` (Bearer: totp_setup token) with `{code}` — confirms TOTP, revokes the setup token, returns `{access_token, refresh_token}`.
5. `POST /auth/refresh` — rotates: old refresh jti goes into Redis blocklist for its remaining lifetime.
6. `POST /auth/logout` — revokes both access + refresh jtis.
7. `POST /invites/` (admin only) — creates an invite; raw token returned **once**, only SHA-256 hash persisted.

### Run tests

Everything runs inside a Python 3.11 docker container (the "cli" profile of `docker-compose.yml`) so the host's Python version doesn't matter.

```bash
cd "/Users/hc_user/Downloads/Niyam AI"
open -a Docker && sleep 8               # start Docker Desktop if it isn't up
docker compose up -d postgres redis     # infra
docker compose build backend            # first run: ~few minutes for bcrypt/cryptography wheels
docker compose run --rm backend alembic upgrade head

docker compose run --rm backend pytest tests/unit -v           # parsers, canonical hashing, auth primitives
docker compose run --rm backend pytest tests/integration -v    # RLS, auth flow, import flow
docker compose run --rm backend pytest -m rls -v               # RLS isolation only
```

### Run the worker + API (dev)

```bash
docker compose up worker                # starts the RQ worker in the foreground
docker compose up api                   # FastAPI on http://localhost:8000
```

### Run the dashboard (dev)

```bash
docker compose up frontend              # Next.js on http://localhost:3000
```

Full dev stack in one line: `docker compose up postgres redis api worker frontend`.

### Run the Playwright smoke

Requires host Node ≥ 18. Seeds via the running backend, so all of `postgres redis api` must be up.

```bash
cd frontend
npm install
npx playwright install chromium
NIYAM_API_BASE=http://localhost:8000 npm run test:e2e
```

### Run the money formatter unit test

```bash
cd frontend
npm install
npm run test:unit
```

---

## Local setup

```bash
# 1. Start Postgres + Redis
docker compose up -d

# 2. Backend deps
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# 3. Apply the initial migration (runs as DB owner `niyam`, superuser in dev,
#    so it can create the `niyam_app` role and manage RLS policies)
cp ../.env.example ../.env    # DATABASE_URL points at owner
alembic upgrade head

# 4. Run the API (once auth ships) as the app role
export DATABASE_URL=$APP_DATABASE_URL
uvicorn app.main:app --reload
```

---

## How RLS is enforced and tested

**Every tenant-scoped table carries `firm_id`** (denormalized). RLS policies are single-column checks against a per-session GUC:

```sql
USING (firm_id = current_setting('app.current_firm_id', true)::uuid)
```

* The FastAPI process connects as `niyam_app`, a NOLOGIN role explicitly created with `NOBYPASSRLS`. Superusers bypass RLS, so migrations (owner) and DBA sessions can maintain data; application code cannot.
* Every request opens a transaction and issues `SET LOCAL app.current_firm_id = '<uuid>'` derived from the authenticated JWT. `SET LOCAL` scopes to the transaction — a leaked connection can't leak firm scope.
* `ca_firm` uses `id = current_setting(...)` (its own tenancy column).
* `rule_pack` is global and read-only for the app role.
* Append-only tables (`readiness_snapshot`, `audit_log`, `consent_log`) grant SELECT + INSERT only, and two BEFORE triggers (`_no_update`, `_no_delete`) block mutation even if grants are later widened by accident.

**Tests** live in `backend/tests/integration/test_rls.py` and prove:

1. `test_select_star_only_returns_own_firm` — pin firm A, wide `SELECT *` returns only firm A rows.
2. `test_buggy_where_naming_other_firm_still_blocked` — a WHERE clause hard-coding firm B still returns zero rows (RLS is applied before the WHERE).
3. `test_insert_with_wrong_firm_id_rejected_by_with_check` — insert firm-B row while pinned to firm A → RLS `WITH CHECK` rejects.
4. `test_missing_firm_guc_returns_zero_rows` — no GUC set → policy returns zero rows (safe fail).
5. `test_audit_log_update_blocked_by_trigger` — trigger raises `table audit_log is append-only`.
6. `test_readiness_snapshot_delete_blocked_by_trigger` — same for snapshots.
7. `test_consent_log_update_blocked_by_trigger` — same for consent.

Run:

```bash
docker compose up -d
cd backend
alembic upgrade head
pytest -m rls -v
```

---

## How to add a rule to the rule pack

Rule packs live in `rule_pack (version TEXT, payload JSONB, active BOOL)`. Only one row can be active at a time (partial unique index). To ship a new rule:

1. Add a new row: `INSERT INTO rule_pack (version, payload, active) VALUES ('1.1.0', '{…}', FALSE);`
2. Add or edit a pure rule function in `backend/app/engines/validation/rules/` matching the pattern `def r00X_name(invoice, ctx) -> Optional[Flag]`. Read tolerances and slabs from `ctx.rule_pack.payload`.
3. Register it in `backend/app/engines/validation/pipeline.py`.
4. Flip the active flag: `UPDATE rule_pack SET active = TRUE WHERE version='1.1.0';` (partial unique index guarantees mutual exclusion — the old row must be flipped off first).
5. New validation runs, reconciliation runs, and readiness snapshots automatically stamp the new `rule_pack_version`. Historical scores stay reproducible because they carry the version they were computed under.

---

## What is stubbed for P2 (with intended contracts)

Every stubbed feature has a clean Python contract at `backend/app/stubs/`. All stubs `raise` on call so P1 code paths never silently succeed against fake data, and every stubbed feature is visibly labelled in the dashboard UI (`<StubBadge>` component). The concrete P2 implementation drops in without changing any caller.

**`app/stubs/gsp_api.py` — GSP (GST Suvidha Provider) integration.** `pull_gstr2b(gstin, period)` initiates a consented GSTN pull via a licensed GSP intermediary and returns raw GSTR-2B JSON as the GSTN emits it. Consent (OTP against the GSTIN's registered mobile) is scoped by `client_id` and logged to `consent_log` before the first pull; subsequent pulls reuse the session token. Every pull writes a `gstn_pull` row with `source='gsp_api'` (P1 imports write `'json_import'`) so the reconciliation engine picks it up unchanged. Also expected: `check_gstin_status(gstin)` powering R009 (the "supplier is cancelled" alert — R002 is the P1 stand-in), and `fetch_filing_status(gstin, period, return_type)` feeding a trailing-window supplier_risk. Rate limits and per-call cost accounting are the GSP layer's responsibility. P1 stubs because GSP access is a licensed, paid integration requiring a signed ASP+GSP contract, sandbox credentials, and per-client production nomination on GSTN.

**`app/stubs/llm_narrator.py` — vernacular narration.** `narrate(facts, language)` accepts a frozen `facts` dict (P&L, tax due, ITC bucket totals, top blockers — all integers in paise, computed by the deterministic engines) plus an ISO language code (`kn`, `hi`, `mr`, `en`) and returns short prose blocks the template engine assembles into the MSME 2-pager. **Hard rule the entire positioning depends on: the LLM never computes or invents a number.** Every rupee figure in the output must be one the caller passed in verbatim — the narrator is a translation/tone layer, nothing more. "Niyam prepares and flags; the CA approves and advises" only holds if numeric authority stays with the deterministic engines. P1 stubs because vernacular narration is a P3 feature; the raw facts already flow through in JSONB (`readiness_snapshot.arithmetic`, `reconciliation_run.summary`), so the narrator drops in without any engine changes.

**`app/stubs/whatsapp.py` — WhatsApp Business API delivery.** `send_report(client_id, pdf_bytes, voice_note_bytes=None)` uploads the CA-approved 2-pager (and optional 60-second voice-note MP3) to WhatsApp Cloud API, addressed to the phone number on `client.metadata.whatsapp_number`, using an approved template from the CA firm's WABA sender ID. The client sees "Message from `<CA firm brand>`" — never "Message from Niyam AI." That's a positioning non-negotiable: the CA looks premium, which is why the CA pays. Also expected: `send_supplier_chase(...)` which MUST respect the `NearMissReview` gate on the CA side — the API here does delivery, never decides to chase. P1 stubs because WABA onboarding is a multi-week bureaucratic pipeline that's only meaningful once we've signed a pilot CA firm as the sender.

**Not-in-P1 features (no stub file; scope-boundary only):**

* **OCR / camera invoice capture** — behaviour-change fallback for the cash-and-paper tail. P4 alongside the MSME mobile app.
* **MSME mobile app** — the owner's glass-pane app (three tiles + task list + ask-my-CA channel).
* **Notice assistant** — P5. The classify-explain-draft flow for GST notices.
* **Advisory nudge engine** — P5. Pattern detectors on 12-month client data → one "ask your CA about…" prompt per month, gated through CA approval.
* **Tally XML bridge** — a companion Windows utility that syncs Tally XML/ODBC to our CSV column contract. P2 scope.

---

## Domain verification needed — agenda for the CA validation meetings

Every item below is a specific statutory detail P1 encoded from public documentation or reasonable defaults, and **every one needs a practicing CA to confirm or overrule before we ship to a first paying customer**. All defaults are config-driven (see `app/rules/default_pack.py`) so a change is a rule-pack version bump, not a code deploy. Grep for `TODO-VERIFY-WITH-CA` to see every touchpoint in code.

**1. HSN slab thresholds (R004).** We assume: turnover ≤ ₹5 cr → min 4 HSN digits, warning; > ₹5 cr → min 6 digits, error. CBIC notifications have shifted this multiple times. Confirm the current threshold, the exact digit count expected for services vs goods, and whether B2C and B2B are treated differently.

**2. Tax-arithmetic rounding tolerance (R006).** Default: ±100 paise (₹1) per invoice. Some CA offices round per-line-item, some per-invoice, some per-supplier per-month. Confirm the practically enforceable tolerance the GST officer will accept without a query.

**3. Expected tax rate set (R006).** Default: 0, 0.1, 0.25, 3, 5, 12, 18, 28 percent. Confirm the current rate schedule for services + goods, and whether "compensation cess" values need to enter the arithmetic check.

**4. Reconciliation fuzzy-match tolerances.** Default: ±5 days on invoice date, ±1% on amount, 0.70 confidence threshold for `probable`. These drive whether an invoice ends up in `probable` (CA reviews) or `supplier_default` (chase). Tune to the false-positive rate the CA can live with — one bad probable per week is fine, one per hour is not.

**5. Readiness score component weights and days-to-due curve.** Default: validation_pass_rate 25, reconciliation_match_rate 40, data_completeness 15, supplier_risk 10, days_to_due 10; linear decay from 100 at 14 days to 0 at due date. This is the number the entire command center sorts by — the CA must feel it reflects real filing readiness.

**6. Due dates for GSTR-1 / GSTR-3B by scheme.** Default: GSTR-1 11th of following month, GSTR-3B 20th, composition scheme = NULL (no monthly return). QRMP filers, IFF (Invoice Furnishing Facility), and threshold-based staggering are all P2 — for a QRMP client, our default due date lies. Confirm the exact due-date matrix for the CA's actual client mix.

**7. Credit / debit note (CDN) handling.** `b2b_entry.note_type` is present in the schema and `cdnr` / `cdnra` sections of the 2B JSON are visible in the raw payload — but P1 **does not parse them and reconciliation does not net CDN adjustments off matched ITC**. Every P1 ITC figure — in the API, dashboard, and any exports — carries "**Before credit/debit note adjustments**". Confirm the netting rule (invoice-level vs supplier-level), the treatment when a note lands in a different period than the underlying invoice, and whether CDN-only 2B entries should surface as their own bucket or fold into `missing_entry`.

**8. GSTIN active-status check (would be R009).** P1 catches malformed GSTINs (R002) but does not verify that a well-formed GSTIN is still active on the GSTN portal. The demo uses R002 as a stand-in for "supplier appears cancelled." The live status check is a stubbed contract at `app/stubs/gsp_api.py::check_gstin_status`; confirm the desired behaviour when a GSTIN is cancelled mid-period (retroactive re-flag of prior matched invoices? or only forward-looking?).

**9. Supplier-risk window.** P1 marks a supplier "risky" for scoring if they appear in the CURRENT period's `supplier_default` bucket. Confirm the correct trailing window (3 months? 6 months? filing-cycle-aware?) and whether an "unresolved" concept (CA can mark a supplier_default row as "reviewed and legitimate") should exclude it from the risk pool.

**10. Duplicate-suspect key (R007).** Default: same `(counterparty_gstin, normalized_invoice_number)` in the period. Confirm whether the invoice date should be part of the key, and how amendments to a booked invoice (change-of-particulars) should present — as a duplicate, as a new invoice, or as an amendment link.

**11. Intra-state vs inter-state derivation (R005).** Default: compare state code from the client's own GSTIN (first 2 digits) vs the counterparty's. This ignores "bill-to vs ship-to" place-of-supply nuances (SEZ, exports, deemed exports, freight). Confirm whether P1's simplified check is safe for the target MSME segment (trading + services) or if we need to handle POS overrides.

**12. Composition-scheme handling.** Client-level `gstin_profile.scheme` is `regular` or `composition`. Composition filers have no monthly returns (only quarterly CMP-08 + annual GSTR-4) — the P1 due-date map returns NULL for composition, meaning the days-to-due component contributes zero. Confirm whether composition clients should even appear in the command center's current-period view, or should be filtered to their own dashboard.

**13. Data-completeness baseline.** Default: current-month invoice count vs simple mean of trailing 3 months. Confirm whether the CA prefers median (more robust to a seasonal spike) or a weighted trend, and whether the baseline should be by invoice count or by ₹ value.

**14. Content-hash normalization rules (dedup).** Default: uppercase, strip separators (`- / . space`), strip leading zeros per digit-run. Confirm this matches what CAs consider "the same invoice" — especially against Tally's quirks with e-invoice IRNs, re-numbered voucher series, and financial-year prefixes.

**15. Two-factor authentication policy.** Mandatory TOTP for CA firm users; SMS OTP is not a P1 option. Confirm this is acceptable to the target CA firm segment or if a SMS-fallback is a deal-breaker.

**16. Data retention + right-to-erasure.** DPDP-shaped table exists (`consent_log`, append-only) but no automatic purge or client-data-export job runs. Confirm the retention window the CA wants offered to their MSMEs, and the "hard delete" mechanics — CASCADE-delete a client, or anonymise?

**Bring these to the meeting. Every one is a rule-pack knob today; every answer is one INSERT INTO `rule_pack` (`version`, `payload`, `active`) + a UPDATE-toggle away.**

---

## Tech stack (fixed)

* Backend: Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2
* Database: Postgres 15+, Row-Level Security on every tenant table
* Queue: **Redis + RQ**. RQ over Celery because P1 has ~5 job types, no beat scheduling needs beyond a nightly cron, and RQ ships with a readable dashboard. If we later need chord/canvas patterns or distributed beat, we migrate.
* Frontend: Next.js (App Router) + TypeScript + Tailwind
* Auth: email+password + TOTP 2FA + JWT (access + refresh)
* Testing: pytest (engines are the most-tested code in the repo); Playwright smoke tests for the dashboard
* Timestamps: UTC in storage, Asia/Kolkata in display. Money: integer paise everywhere.
