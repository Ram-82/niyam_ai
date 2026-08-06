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

## First-time deploy checklist

1. Provision Postgres 15 and Redis 7. Note the DSNs.
2. Generate a 32+ byte random `JWT_SECRET`. Store in your secrets
   manager.
3. If enabling narrator/whatsapp, provision `ANTHROPIC_API_KEY` and
   `WHATSAPP_*` values.
4. Populate the deploy-side `.env` from `.env.example`. Point at the
   real DBs.
5. `docker run --rm --env-file .env <image> alembic upgrade head`.
6. `docker run --rm --env-file .env <image>` — API comes up.
7. Bootstrap the first firm + admin via a one-shot script (there's no
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
