# Niyam AI — P1 MVP

GST pre-filing intelligence for CA firms. P1 ships the **found-money engine**: purchase-register import, GSTR-2B import, deterministic validation, reconciliation with a 4-bucket ITC summary, and a filing-readiness score — surfaced in a Next.js CA dashboard.

> Positioning: **Niyam prepares and flags. The CA approves and advises.** The platform never files on its own judgment.

---

## Status

* **Step 1** ✅ Repo skeleton + Alembic initial migration.
* **Step 2** ✅ SQLAlchemy models + firm-scoped session helper + RLS isolation tests (`backend/tests/integration/test_rls.py`). Run with `pytest -m rls` after `docker compose up -d && alembic upgrade head`.
* Steps 3–10 pending. See workspace TaskList.

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

## What is stubbed for P2

The following are behind clean interfaces in `backend/app/stubs/`. They log a clear WARNING when called and are labeled "stubbed" in the dashboard UI:

* **GSP API** (`stubs/gsp_api.py`) — live GSTR-2B pulls. P1 accepts 2B via JSON upload; the same `GstnPuller` interface will point at a licensed GSP in P2.
* **LLM narrator** (`stubs/llm_narrator.py`) — vernacular 2-pager prose. P1 has no report generation.
* **WhatsApp delivery** (`stubs/whatsapp.py`) — approved-report send.
* **OCR** — no camera/PDF invoice extraction in P1.
* **MSME mobile app** — not built in P1.
* **Notice assistant** and **advisory nudge engine** — deferred to P4/P5.

---

## Domain verification needed

Items where GST statutory detail is ambiguous and must be confirmed with a practicing CA before we ship. Each is implemented config-driven (in rule_pack payload) and marked with `TODO-VERIFY-WITH-CA` in code:

* Turnover slabs that decide HSN mandatory / optional and the digit count (R004).
* Tax arithmetic rounding tolerance in paise (R006).
* Date window for fuzzy invoice-date matching (reconciliation Pass 2) — currently ±5 days.
* Amount tolerance % for fuzzy match — currently ±1%.
* Confidence threshold for `probable` vs discard.
* Weights for the five scoring inputs; days-to-due-date modifier curve.
* Due dates for GSTR-1 / GSTR-3B by scheme.
* **Credit/debit note (CDN) handling.** `b2b_entry.note_type` is present in the schema but P1 does not parse the CDN sections of the 2B JSON, and reconciliation does not net CDN adjustments off matched ITC. **Every P1 ITC summary — in the API, dashboard, and any exports — is labeled "before credit/debit note adjustments."** Confirm with a CA: the correct netting rule (invoice-level vs supplier-level), the treatment when a note lands in a different period than the underlying invoice, and whether CDN-only 2B entries should surface in the "missing_entry" bucket or a separate bucket.

---

## Tech stack (fixed)

* Backend: Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2
* Database: Postgres 15+, Row-Level Security on every tenant table
* Queue: **Redis + RQ**. RQ over Celery because P1 has ~5 job types, no beat scheduling needs beyond a nightly cron, and RQ ships with a readable dashboard. If we later need chord/canvas patterns or distributed beat, we migrate.
* Frontend: Next.js (App Router) + TypeScript + Tailwind
* Auth: email+password + TOTP 2FA + JWT (access + refresh)
* Testing: pytest (engines are the most-tested code in the repo); Playwright smoke tests for the dashboard
* Timestamps: UTC in storage, Asia/Kolkata in display. Money: integer paise everywhere.
