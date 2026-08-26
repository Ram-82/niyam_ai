# Restore drill — Niyam AI

**Status:** `NOT YET EXECUTED`. Do not treat any wall-clock or row-count
number in this document as authoritative until an operator has run the
procedure end-to-end and pasted the real output into
[§7 Drill log](#7-drill-log) below.

---

## 1. What this doc is (and isn't)

Point-in-time recovery of Niyam's Postgres is a **Supabase-managed
platform feature**, not something the repo controls. There is no
`wal_level`/`archive_command` in this codebase (`grep` in
`docs/audit/p3-baseline.md §3` confirms) and no application-owned
backup script would be honest — writing one would suggest Niyam owns a
promise it does not own.

What this drill *does* verify — the only questions we can actually
answer without touching Supabase's control plane:

1. **Does a Supabase-provisioned restore round-trip cleanly?** i.e. we
   can pull a `pg_dump` from a Supabase project and reload it into a
   scratch Postgres.
2. **Does the app come up against that restored state?** Alembic sees
   the schema as `head`, the integration suite runs green, RLS is
   still enforced, row counts on the load-bearing tables match what
   we exported.

Everything upstream of that — Supabase's WAL archival cadence, PITR
window (24h vs 7d vs 30d depending on plan), backup encryption at
rest, restore SLA under vendor incident — is a Supabase business-plan
question the owner must confirm with Supabase support. Cite the
answers in [§6 Vendor SLA to confirm](#6-vendor-sla-to-confirm) below
before this doc leaves `NOT YET EXECUTED`.

---

## 2. Prerequisites

- Local Docker with the repo's `docker-compose.yml` (postgres:15 image).
- Supabase project credentials with **read-only** access — `pg_dump`
  needs no more than `SELECT` on tenant tables.
- Enough disk for the dump. A pilot-scale firm is single-digit MB;
  reserve ~5× the reported project size as headroom.
- No pytest run in progress against the local Postgres (this drill
  will destroy that database).

TODO-VERIFY-WITH-OWNER: production database URL and read-only role
name. Do not paste live credentials into this file — reference the
secrets manager entry instead.

---

## 3. Run the drill

### 3.1 Export from Supabase

```bash
# Substitute the read-only role and prod project URL.
export SUPABASE_URL='postgresql://readonly@db.<project-ref>.supabase.co:5432/postgres'
pg_dump \
  --no-owner --no-privileges \
  --format=custom \
  --file=/tmp/niyam-restore-drill.dump \
  "$SUPABASE_URL"
```

Record wall-clock. Anything meaningfully over 5 minutes at pilot
scale means the size or index count has grown — flag it before it
becomes an incident window.

### 3.2 Wipe the local scratch database

```bash
cd <repo-root>
docker compose down -v          # -v removes the niyam_pg volume
docker compose up -d postgres
# Wait for pg_isready
until docker compose exec -T postgres pg_isready -U niyam -d niyam; do
  sleep 2
done
```

### 3.3 Restore into the scratch database

```bash
docker compose cp /tmp/niyam-restore-drill.dump postgres:/tmp/
docker compose exec -T postgres pg_restore \
  --no-owner --no-privileges \
  --dbname=niyam \
  /tmp/niyam-restore-drill.dump
```

### 3.4 Sanity check — schema is at head

```bash
docker compose run --rm -T backend alembic current
# Expected: 0024_narrator_cost_and_budget (head) — bump this line on
# every new migration so a wrong-head restore fails loudly here.
```

### 3.5 Sanity check — row counts on the load-bearing tables

```bash
docker compose exec -T postgres psql -U niyam -d niyam -c "
  SELECT 'filing_run' AS t, COUNT(*) FROM filing_run
  UNION ALL SELECT 'audit_log', COUNT(*) FROM audit_log
  UNION ALL SELECT 'reconciliation_run', COUNT(*) FROM reconciliation_run
  UNION ALL SELECT 'narration_run', COUNT(*) FROM narration_run
  UNION ALL SELECT 'narrator_call_log', COUNT(*) FROM narrator_call_log
  UNION ALL SELECT 'legal_acceptance', COUNT(*) FROM legal_acceptance
  UNION ALL SELECT 'gsp_call_log', COUNT(*) FROM gsp_call_log;
"
```

Compare against the same query run against Supabase (via
`psql "$SUPABASE_URL"` with the same statement) *before* §3.1. Deltas
should be zero.

### 3.6 Sanity check — integration suite green against restored data

```bash
# The suite's clean_db fixture TRUNCATEs tenant tables between tests
# — so this run does NOT preserve the restored rows. Run it only to
# prove that the restored *schema* passes; row-level checks must
# happen before this step.
docker compose run --rm -T backend pytest -q --timeout=30 -m 'not quarantine'
```

### 3.7 Sanity check — RLS is still enforced

```bash
# Set an arbitrary firm_id, then verify a query as niyam_app cannot
# see rows from a different firm. Uses two random firm_ids picked
# from ca_firm.
docker compose exec -T postgres psql -U niyam -d niyam <<'SQL'
  SET ROLE niyam_app;
  SELECT set_config('app.current_firm_id',
    (SELECT id::text FROM ca_firm LIMIT 1 OFFSET 0), true);
  SELECT COUNT(*) FROM audit_log; -- should equal firm-1's count
  SELECT set_config('app.current_firm_id',
    (SELECT id::text FROM ca_firm LIMIT 1 OFFSET 1), true);
  SELECT COUNT(*) FROM audit_log; -- should equal firm-2's count
  RESET ROLE;
SQL
```

If both queries return the same number, RLS is not enforced — the
restore has landed in a database where `FORCE ROW LEVEL SECURITY` did
not carry over. Do not sign off the drill; investigate first.

---

## 4. Definition of done

The drill counts as executed once **all** of the following are true
and pasted into [§7 Drill log](#7-drill-log):

- [ ] `pg_dump` completed without errors, wall-clock recorded.
- [ ] `pg_restore` completed without errors, wall-clock recorded.
- [ ] `alembic current` reported the same revision id we expect on
      the branch that produced the dump.
- [ ] Row counts on `filing_run`, `audit_log`, `reconciliation_run`,
      `narration_run`, `narrator_call_log`, `legal_acceptance`,
      `gsp_call_log` matched pre-export values.
- [ ] Integration suite passed against the restored schema.
- [ ] RLS check returned different row counts for the two firms
      (i.e. isolation still holds).

Until then the status header stays `NOT YET EXECUTED`.

---

## 5. Rollback / cleanup

The drill destroys the local scratch database. To return the local
dev environment to a working state:

```bash
cd <repo-root>
docker compose down -v
docker compose up -d postgres
docker compose run --rm -T backend alembic upgrade head
```

If a dev seed is needed after this, re-run the app's usual seeding
script (there is no shared repo-level seeder as of migration 0024).

---

## 6. Vendor SLA to confirm

TODO-VERIFY-WITH-OWNER: fill these in from Supabase support / plan
page. Numbers below are placeholders; do not treat as chosen.

| Question                          | Supabase answer                | Where confirmed |
|-----------------------------------|--------------------------------|-----------------|
| Backup cadence                    | `TODO-VERIFY-WITH-OWNER`       |                 |
| PITR retention window             | `TODO-VERIFY-WITH-OWNER`       |                 |
| Encryption at rest for backups    | `TODO-VERIFY-WITH-OWNER`       |                 |
| Restore SLA during vendor incident| `TODO-VERIFY-WITH-OWNER`       |                 |
| Region of the backup copy         | `TODO-VERIFY-WITH-OWNER`       |                 |

---

## 7. Drill log

_Blank until the drill runs. Paste real command output below (dates,
wall-clocks, row counts, and any deviation from steps §3.1–3.7).
Do not paraphrase the output — a paraphrase invites drift._

```
--- placeholder ---
Drill has not yet been executed.
```
