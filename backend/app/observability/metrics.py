"""Prometheus metrics registry — the /metrics endpoint's source of truth.

Phase 1.6 (P3). Chose Prometheus over OTel because:

* Single in-process default registry — no collector process to run, no
  exporter to configure. A prod scrape is one HTTP endpoint away.
* Standard text format that every prod monitoring stack (Grafana Cloud,
  Managed Prometheus, Datadog's Prom scraper) already ingests.
* We do NOT have the operational budget for OTel yet (no collector, no
  backend, no tracing UX). Prometheus gives us the four SLO-shaped
  metrics we need today and can be complemented by OTel later without
  a rewrite — the metric names below map 1:1 to OTel counters if we
  ever migrate.

Metrics defined here (all prefixed ``niyam_`` for scrape hygiene):

* :data:`http_requests_total` — counter{method, route, status}
* :data:`http_request_duration_seconds` — histogram{method, route}
* :data:`narrator_cost_paise_total` — counter{model}, unit=paise
* :data:`narrator_calls_total` — counter{model, outcome}
* :data:`gsp_pull_total` — counter{outcome}
* :data:`auth_failures_total` — counter{reason}
* :data:`auth_lockouts_total` — counter (unlabelled — a lockout is a
  lockout)

Route labelling uses FastAPI's matched route template (``/clients/{id}``)
not the raw URL — unbounded cardinality on route labels is the classic
Prometheus pitfall and pages sooner than any real incident.

Import this module from the middleware and from wire points that need
to increment counters. The default registry is module-global — do NOT
create a new registry per test; the metric objects live for the
process lifetime.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram


# HTTP surface — populated by RequestIdMiddleware after every response.
http_requests_total = Counter(
    "niyam_http_requests_total",
    "Total HTTP requests handled, labelled by method, matched route "
    "template, and status code.",
    ["method", "route", "status"],
)

http_request_duration_seconds = Histogram(
    "niyam_http_request_duration_seconds",
    "HTTP request wall-clock duration in seconds, labelled by method "
    "and matched route template. Buckets tuned for a p95 target in the "
    "hundreds of ms — coarser at the tail so a slow reconciliation "
    "run does not flood the histogram.",
    ["method", "route"],
    buckets=(
        0.010, 0.025, 0.050, 0.100, 0.250, 0.500,
        1.0, 2.5, 5.0, 10.0, 30.0,
    ),
)

# Narrator cost meter — driven from ``narrator/service.py::_log_call``.
# Sums per model so a per-firm breakdown is available via the
# aggregation API; the /metrics view is process-wide.
narrator_cost_paise_total = Counter(
    "niyam_narrator_cost_paise_total",
    "Sum of narrator_call_log.cost_paise per model since process start. "
    "Unpriced calls (cost_paise IS NULL) do not increment.",
    ["model"],
)

narrator_calls_total = Counter(
    "niyam_narrator_calls_total",
    "Narrator adapter invocations, labelled by model and outcome "
    "('success', 'hallucination', 'adapter_error', 'disabled', "
    "'budget_exhausted').",
    ["model", "outcome"],
)

# GSP surface — populated by the GSP call sites in ``app.api.gsp`` /
# ``app.gsp.service``. Outcome buckets match ``gsp_call_log.status``
# ('success', 'auth_error', 'rate_limited', 'error') so the counter
# lines up with the audit log.
gsp_pull_total = Counter(
    "niyam_gsp_pull_total",
    "GSP pull attempts, labelled by outcome from gsp_call_log.status.",
    ["outcome"],
)

# Auth — failures and lockouts. Kept as two counters so the alert rule
# on lockouts (a real user-visible incident) doesn't need to filter a
# noisy failure counter with typos.
auth_failures_total = Counter(
    "niyam_auth_failures_total",
    "Failed authentication attempts, labelled by reason "
    "('bad_password', 'no_such_user', 'totp_mismatch', 'refresh_revoked', "
    "'lockout_active').",
    ["reason"],
)

auth_lockouts_total = Counter(
    "niyam_auth_lockouts_total",
    "Users transitioned into the lockout state (5 failures / 15 min).",
)


__all__ = [
    "auth_failures_total",
    "auth_lockouts_total",
    "gsp_pull_total",
    "http_request_duration_seconds",
    "http_requests_total",
    "narrator_calls_total",
    "narrator_cost_paise_total",
]
