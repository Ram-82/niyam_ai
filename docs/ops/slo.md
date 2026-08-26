# SLOs and paging condition — Niyam AI

**Status:** proposal. Every numeric threshold below is
`TODO-SET-WITH-OWNER`. No traffic data exists to justify a chosen
number; treat these as placeholders pending owner + pilot-firm
signal.

---

## 1. What this doc is (and isn't)

Phase 1.6 (P3) requires **one paging condition** in code + doc. This
file defines that one condition. On-call rotation, escalation policy,
and paging-vendor choice are organisational decisions, not code, and
are explicitly out of scope for a repo-level SLO doc — cite them
elsewhere.

Do not add SLOs here that we do not intend to alert on. An SLO with
no page is a metric.

---

## 2. Why Prometheus, not OTel

Two lines per spec §3.1.6:

1. **In-process registry, single scrape endpoint.** No collector
   process to run, no exporter to configure. A prod Grafana Cloud /
   Datadog / Managed Prometheus scrape is one HTTP call away.
2. **We don't have the operational budget for OTel yet** — no
   collector, no tracing UX, no backend selection. Metric names in
   `app/observability/metrics.py` map 1:1 to OTel counters if we
   migrate later, so this choice does not paint us into a corner.

---

## 3. The one paging condition

**Trigger a page** when, for any 5-minute window:

- the `/health` probe has returned non-200 more than once,
  **OR**
- p95 of `niyam_http_request_duration_seconds` on either
  `POST /reconciliation/run` or `POST /filings/generate` exceeds
  `TODO-SET-WITH-OWNER` seconds.

Justification for those two routes:

- **Reconciliation** is the load-bearing engine — a slow reconciliation
  blocks the CA workflow for every open filing.
- **Filing generation** is the throughput-critical action that
  precedes the actual GSTN submission window; a slow filing route
  can miss a statutory due date.

Auth failure spikes and GSP outcome failures are dashboard signals,
not paging signals — they are noisy under normal operation and a
false page here would train ignore behaviour. Add them to a
Grafana dashboard, do not page on them.

### 3.1 Thresholds to set

| Metric                                          | Placeholder | Owner action              |
|-------------------------------------------------|-------------|---------------------------|
| p95 `POST /reconciliation/run` latency (5-min)  | `?` seconds | `TODO-SET-WITH-OWNER`     |
| p95 `POST /filings/generate` latency (5-min)    | `?` seconds | `TODO-SET-WITH-OWNER`     |
| `/health` non-200 count (5-min)                 | > 1         | Fixed, no action required |
| SLO burn window (fast alert)                    | `?` minutes | `TODO-SET-WITH-OWNER`     |

The p95 numbers require production traffic to justify. Do NOT pick a
number from a synthetic load test and treat it as chosen — that is
worse than no threshold, because it looks decided.

---

## 4. Signals wired into `/metrics` (for the dashboard, not the page)

These exist in `app/observability/metrics.py` and are labelled to
support the dashboard queries you would build first:

- `niyam_http_requests_total{method, route, status}` — error rate:
  `sum(rate(...{status=~"5.."}[5m])) by (route)`.
- `niyam_http_request_duration_seconds{method, route}` — histogram
  used by the p95 conditions above.
- `niyam_gsp_pull_total{outcome}` — vendor-error split
  (auth / rate-limited / other) for the GSP dashboard.
- `niyam_narrator_calls_total{model, outcome}` +
  `niyam_narrator_cost_paise_total{model}` — cost trend + failure kinds.
- `niyam_auth_failures_total{reason}` +
  `niyam_auth_lockouts_total` — brute-force early warning; graph, do
  not page (per §3 above).

---

## 5. Explicitly out of scope

- **On-call rotation**, escalation policy, and paging vendor choice —
  organisational decisions. Note in an ops runbook, not here.
- **SLOs for external vendor endpoints** (GSP, Anthropic, Meta) —
  they set their own SLA. We track their outcomes with counters, we
  do not page on them.
- **Load testing** — no production traffic to model. Explicitly
  deferred (P3_BUILD_PROMPT §7).
