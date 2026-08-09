# Deployment

Reference for running Niyam AI in production. Development runs off
`docker-compose.yml`; this doc covers what changes when you leave
localhost.

## Runtime shape

- **API container** — `backend/Dockerfile.prod`. Multi-stage image, runs
  gunicorn with uvicorn workers as UID 10001. Expose 8000/tcp behind a
  TLS terminator (see below). Set `WEB_WORKERS` to `(2 * cpu) + 1`.
- **Worker container** — same image; overrides CMD to
  `python -m app.workers.worker`. Shares `/data/uploads` with the API
  container via a persistent volume.
- **Postgres 15** — RLS is *required*; the app assumes migration 0001
  has been applied and the `niyam_app` role exists.
- **Redis 7** — used for JWT revocation, login lockouts, GSP OTP
  cooldowns, and the RQ queue. Single instance is fine for one firm;
  cluster for multi-firm scale.
- **gsp-mock container** — dev/CI only. Do not run in prod; point
  `GSP_MODE=prod` + `GSP_BASE_URL` at the real GSP.

## Environment variables

Every var the app reads is documented in `.env.example` at the repo
root, grouped by concern. Two invariants worth restating:

- `JWT_SECRET` — rotate this and every outstanding token is invalidated.
  Plan the rotation during a maintenance window.
- `GSP_ENCRYPTION_KEYS` — rotating fernet keys used to encrypt GSP
  session blobs at rest. First key is the write key; older keys stay in
  the list until every ciphertext has been rewritten.

## TLS termination

The container serves plain HTTP on 8000. TLS terminates one hop up:

- **Kubernetes** — an ingress controller (nginx-ingress, Traefik,
  cloud-native ALB) with a cert-manager-issued certificate. Ensure
  `X-Forwarded-Proto` and `X-Forwarded-For` are set; gunicorn is
  launched with `--forwarded-allow-ips=*` so those headers reach the
  request.
- **Bare VM** — Caddy or nginx in front. Caddy autoprovisions certs
  from Let's Encrypt; nginx needs certbot.
- **Behind Cloudflare / CDN** — set full-strict SSL and pin the origin
  cert to Cloudflare's IP ranges. Do *not* set `--forwarded-allow-ips=*`
  in that topology — pin it to the CDN's egress ranges instead so a
  spoofed `X-Forwarded-For` cannot poison audit logs.

## Health probes

- `/livez` — always 200 unless the process is unresponsive. Do NOT
  point a readiness probe at this; it will keep sending traffic to a
  pod that can't reach the DB.
- `/readyz` — returns 503 when Postgres or Redis is unreachable. Body
  carries per-dependency status for debugging.
- `/health` — legacy alias for compose healthchecks + the frontend
  smoke; equivalent to `/livez`.

Kubernetes example:

```yaml
livenessProbe:
  httpGet: { path: /livez, port: 8000 }
  periodSeconds: 15
readinessProbe:
  httpGet: { path: /readyz, port: 8000 }
  periodSeconds: 5
  failureThreshold: 3
```

## Database migrations

Alembic manages the schema. Migrations **must run before** the API
container starts accepting traffic; the app does not auto-migrate.

### Bare VM / docker-compose

Run as a one-shot step in your deploy script before restarting the API:

```bash
docker run --rm --env-file .env <image> alembic upgrade head
```

Or with `docker compose`:

```bash
docker compose run --rm api alembic upgrade head
docker compose up -d api worker
```

### Kubernetes

Use an init container on the API Deployment so the rollout blocks until
the migration succeeds:

```yaml
initContainers:
  - name: migrate
    image: <same-api-image>
    command: ["alembic", "upgrade", "head"]
    envFrom:
      - secretRef:
          name: niyam-env
containers:
  - name: api
    image: <same-api-image>
    # ...
```

This ensures:
- Migrations complete (or the rollout stalls) before the new pods
  become ready.
- The old pods keep serving until the new pods pass readiness; the
  migration runs exactly once per rollout, not once per replica.

### Multi-step schema changes

For zero-downtime deploys, break backwards-incompatible changes across
two releases:

1. **Release N** — add the new column / table (nullable or with
   default). Both old and new code work.
2. **Release N+1** — backfill data, add the `NOT NULL` constraint, drop
   the old column. Only new code runs.

## Redis persistence

Redis is used for JWT revocation, login lockout counters, GSP OTP
cooldowns, and the RQ job queue. In production, data loss on Redis
restart has concrete consequences:

- **JWT revocation** — a revoked token becomes valid again if its JTI
  disappears. An attacker with a stolen token could regain access.
- **RQ queue** — in-flight import jobs are lost; users must re-upload.
- **Lockout counters** — wiped; brute-force windows reset.

**Required configuration** — enable *at least* AOF (append-only file)
persistence:

```
# redis.conf
appendonly yes
appendfsync everysec     # 1-second durability window; acceptable for
                          # auth workloads. Use "always" for maximum
                          # safety at the cost of write throughput.
```

RDB snapshots (`save 900 1` etc.) are not sufficient alone — they
tolerate up to the snapshot interval of data loss. For managed Redis
(ElastiCache, Upstash, Redis Cloud) enable the AOF-equivalent
persistence tier in your provider's settings.

## First-time deploy checklist

1. Provision Postgres 15 and Redis 7. Note the DSNs.
2. Enable AOF persistence on Redis (see above).
3. Generate a 32+ byte random `JWT_SECRET`. Store in your secrets
   manager.
4. If enabling narrator/whatsapp, provision `ANTHROPIC_API_KEY` and
   `WHATSAPP_*` values.
5. Populate the deploy-side `.env` from `.env.example`. Point at the
   real DBs.
6. Run `alembic upgrade head` (see migration section above).
7. Start the API + worker containers.
8. Bootstrap the first firm + admin via a one-shot script (there's no
   self-serve signup yet; see Tier 2 roadmap).

## Log shape

Every log line is JSON:

```
{"ts":"2026-08-06T13:05:30.213Z","level":"INFO","logger":"niyam.request",
 "message":"request","request_id":"...","method":"GET","path":"/livez",
 "status":200,"duration_ms":146}
```

Ship stdout to your aggregator (CloudWatch, Loki, Datadog). The
`request_id` field is the same value echoed back to the client in the
`X-Request-Id` response header, so a user bug report and a log line
correlate directly.
