# Backup + restore

Niyam AI keeps every meaningful piece of state in Postgres — reconciled
invoices, filings, audit trail, delivery attempts, GSP session blobs.
Redis is transient (JWT revocation, lockout counters, RQ queue). Losing
Redis means users need to log in again; losing Postgres means losing
the firm. Back up accordingly.

## What to back up

- **Postgres** — full logical backup with `pg_dump`. Include the schema,
  every table, and the two custom roles (`niyam_app` and any owner).
- **Uploaded files** — everything under `UPLOAD_DIR` (default
  `/data/uploads`). Referenced by `import_job.filename`; losing them
  breaks the "download original" affordance on the imports page.
- **Nothing from Redis.** Rebuildable from scratch on any restart.

## Backup script

Run daily under systemd/cron/k8s CronJob. Use a role that can `SELECT`
every table (the owner is the safe choice; `niyam_app` cannot read
`audit_log` past its own firm boundary and would produce a lopsided
dump).

```bash
#!/usr/bin/env bash
set -euo pipefail

TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="/backups/niyam"
mkdir -p "${DEST}"

# --clean + --if-exists so restore is idempotent.
# --format=custom keeps the archive parseable by pg_restore -j (parallel).
pg_dump \
  --host="${POSTGRES_HOST}" \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --format=custom \
  --clean --if-exists \
  --no-owner \
  --file="${DEST}/niyam-${TS}.pgdump"

# Uploaded files. Prefer versioned S3 sync in prod; tar for on-prem.
tar -czf "${DEST}/uploads-${TS}.tar.gz" -C /data uploads

# Retention: keep 30 daily, 12 monthly, 3 yearly. Adjust to compliance
# needs — GST record retention is generally 6 years in India.
find "${DEST}" -name 'niyam-*.pgdump' -mtime +30 -delete
find "${DEST}" -name 'uploads-*.tar.gz' -mtime +30 -delete
```

## Restore drill

Run this on a scratch DB *quarterly*. A backup you have not restored is
a hope, not a backup.

```bash
# 1. Provision a scratch Postgres instance.
export SCRATCH_URL=postgresql://niyam:niyam@scratch:5432/niyam

# 2. Create the roles the app expects. Migration 0001 creates niyam_app,
#    but pg_restore of --no-owner data will not — so bootstrap first.
psql "${SCRATCH_URL}" -c "CREATE ROLE niyam_app NOLOGIN NOINHERIT;"

# 3. Restore.
pg_restore \
  --dbname="${SCRATCH_URL}" \
  --clean --if-exists \
  --no-owner \
  --jobs=4 \
  /backups/niyam/niyam-<latest>.pgdump

# 4. Restore uploads to the mount point.
tar -xzf /backups/niyam/uploads-<latest>.tar.gz -C /data

# 5. Point a Niyam API container at ${SCRATCH_URL} and hit /readyz.
#    Then log in with a known admin and eyeball command-center: rows
#    should be identical to the source system.
```

## RPO / RTO planning

- **RPO** — daily backup = up to 24h of data lost worst case. For CA
  firms during filing week, tighten to hourly WAL archiving (pg_basebackup
  + WAL-G/pgbackrest). Streaming replication removes the RPO gap.
- **RTO** — a fresh Postgres pod + `pg_restore -j 4` on a mid-sized
  firm's data takes minutes, not hours. Restoring uploads takes as long
  as your `tar` throughput.

## Point-in-time recovery

For real deployments, pair `pg_dump` daily backups with continuous WAL
archiving. WAL-G / pgbackrest / cloud-managed Postgres all provide
PITR; picking one is a deployment-topology decision, not a Niyam-
specific one.

## Encryption at rest

`pg_dump` output contains every audit log entry, every invoice, every
GSP session blob. Encrypt at rest (KMS-envelope encryption on S3,
LUKS/cloud disk encryption for on-prem). The GSP session blobs
themselves are Fernet-encrypted via `GSP_ENCRYPTION_KEYS`, so leaked
backups don't leak GSP OTPs unless the key list also leaks.
