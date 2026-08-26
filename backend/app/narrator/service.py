"""Narrator orchestration + retry policy + audit trail.

Entry points:

* :func:`get_adapter` — returns a :class:`Narrator` per ``settings.narrator_mode``.
* :func:`narrate_for_period` — the full flow that the API calls:
    facts_builder → adapter.narrate → validator → (retry once on
    hallucination) → persist to narration_run → return NarrationOutput.

Retry policy: on a first-attempt ``NumberHallucination``, we retry once
against the same adapter with a stricter reminder appended to the
system prompt. A second hallucination bails loudly — the CA sees a
"narration failed, generate again" surface, never mock prose passed off
as machine output.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.auth import audit
from app.config import settings
from app.db import firm_scoped_session
from app.narrator import pricing, validator
from app.narrator.facts_builder import FactsUnavailable, build_facts
from app.narrator.mock_adapter import MockNarrator
from app.narrator.types import (
    Language,
    Narrator,
    NarratorBudgetExhausted,
    NarratorDisabled,
    NarratorError,
    NarrationFacts,
    NarrationOutput,
    NumberHallucination,
    TokenUsage,
)


log = logging.getLogger("niyam.narrator.service")


def get_adapter() -> Narrator:
    """Return the adapter for ``settings.narrator_mode``.

    Raises :class:`NarratorDisabled` when the feature flag is off, so
    callers can render "narration is not enabled for this environment"
    without leaking which adapter would have run.
    """
    if not settings.narrator_enabled:
        raise NarratorDisabled(
            "narrator disabled (set NARRATOR_ENABLED=1 to enable)"
        )
    if settings.narrator_mode == "mock":
        return MockNarrator()
    if settings.narrator_mode == "anthropic":
        # Local import so a mock-mode deployment does not need the SDK.
        from app.narrator.anthropic_adapter import AnthropicNarrator

        return AnthropicNarrator(
            api_key=settings.anthropic_api_key,
            model=settings.narrator_model,
        )
    if settings.narrator_mode == "gemini":
        from app.narrator.gemini_adapter import GeminiNarrator

        return GeminiNarrator(
            api_key=settings.gemini_api_key,
            model=settings.narrator_model,
        )
    raise NarratorError(
        f"unknown NARRATOR_MODE={settings.narrator_mode!r} "
        f"(expected mock|anthropic|gemini)"
    )


def _to_blocks(out: NarrationOutput) -> dict[str, str]:
    return {
        "page1_health": out.page1_health,
        "page1_tax_position": out.page1_tax_position,
        "page2_attention": out.page2_attention,
        "page2_ask_your_ca": out.page2_ask_your_ca,
    }


def _call_adapter(
    adapter: Narrator,
    facts: NarrationFacts,
    language: Language,
    *,
    strict: bool,
) -> NarrationOutput:
    """Adapters vary in whether they accept ``strict_reminder``. We
    call through in a way that supports both."""
    call = getattr(adapter, "narrate")
    try:
        return call(facts, language, strict_reminder=strict)  # type: ignore[call-arg]
    except TypeError:
        # Mock adapter has the simple signature.
        return call(facts, language)


def _facts_to_dict(facts: NarrationFacts) -> dict:
    """JSON-safe dict for audit persistence."""
    return {
        "period": facts.period,
        "return_type": facts.return_type,
        "firm_name": facts.firm_name,
        "client_name": facts.client_name,
        "sales_paise": facts.sales_paise,
        "purchases_paise": facts.purchases_paise,
        "margin_paise": facts.margin_paise,
        "tax_paid_paise": facts.tax_paid_paise,
        "tax_due_paise": facts.tax_due_paise,
        "itc": {
            "matched_paise": facts.itc_matched_paise,
            "probable_paise": facts.itc_probable_paise,
            "supplier_default_paise": facts.itc_supplier_default_paise,
            "missing_entry_paise": facts.itc_missing_entry_paise,
            "supplier_default_count": facts.itc_supplier_default_count,
        },
        "readiness_score": facts.readiness_score,
        "days_to_due": facts.days_to_due,
        "top_blockers": [
            {
                "kind": b.kind,
                "owner": b.owner,
                "description": b.description,
                "paise_impact": b.paise_impact,
            }
            for b in facts.top_blockers
        ],
        "rule_pack_version": facts.rule_pack_version,
    }


def _persist_run(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    return_type: str,
    period: str,
    language: str,
    facts: NarrationFacts,
    output: NarrationOutput,
    generated_by: Optional[str | uuid.UUID],
) -> uuid.UUID:
    """Insert one narration_run row + one audit_log row.

    The table is APPEND ONLY (see migration 0009); a CA edit of the
    prose happens on a separate ``narration_edit`` row (not built here
    yet) referring back by narration_run_id.
    """
    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text(
                """
                INSERT INTO narration_run (
                    firm_id, gstin_profile_id, return_type, period,
                    language, provider, model,
                    facts, output, generated_by
                ) VALUES (
                    :fid, :gpid, :rt, :p,
                    :lang, :prov, :model,
                    CAST(:facts AS JSONB), CAST(:output AS JSONB), :gb
                )
                RETURNING id
                """
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gstin_profile_id),
                "rt": return_type,
                "p": period,
                "lang": language,
                "prov": output.provider,
                "model": output.model,
                "facts": json.dumps(_facts_to_dict(facts)),
                "output": json.dumps(
                    {
                        "page1_health": output.page1_health,
                        "page1_tax_position": output.page1_tax_position,
                        "page2_attention": output.page2_attention,
                        "page2_ask_your_ca": output.page2_ask_your_ca,
                    }
                ),
                "gb": str(generated_by) if generated_by else None,
            },
        )
        run_id = row.scalar_one()
        audit.record(
            db,
            firm_id=firm_id,
            actor_user_id=generated_by,
            action="narration.generated",
            entity_type="gstin_profile",
            entity_id=gstin_profile_id,
            metadata={
                "narration_run_id": str(run_id),
                "period": period,
                "return_type": return_type,
                "language": language,
                "provider": output.provider,
                "model": output.model,
            },
        )
    return run_id


def _log_call(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    provider: str,
    model: str,
    attempt: int,
    language: str,
    succeeded: bool,
    error_kind: Optional[str],
    usage: TokenUsage,
    started_at: float,
) -> None:
    """Insert one narrator_call_log row.

    Called once per adapter invocation — including retries and failures.
    A hallucination that gets retried produces TWO rows (attempt=1
    logged as succeeded=false + error_kind='hallucination', attempt=2
    logged with the retry's outcome). Matches gsp_call_log's
    per-call granularity so cost dashboards can distinguish
    "one narration cost me 2 API calls" from "one narration = one call".
    """
    # cost_paise: None whenever the model is unpriced OR no tokens were
    # reported (mock adapter / failed attempts with no usage). NULL in
    # the log so the aggregation surfaces "unpriced" honestly instead
    # of a spurious ₹0. When we DO have a cost, we also stamp the
    # pricing_effective_from so a later audit can tell WHICH pricing
    # table produced the number.
    cost_paise: Optional[int] = None
    pricing_effective_from = None
    if usage.input_tokens is not None or usage.output_tokens is not None:
        cost_paise = pricing.estimate_cost_paise(
            model,
            {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_input_tokens": usage.cache_read_input_tokens,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens,
            },
        )
        if cost_paise is not None:
            pricing_effective_from = pricing.PRICING_EFFECTIVE_FROM

    with firm_scoped_session(firm_id) as db:
        db.execute(
            text(
                """
                INSERT INTO narrator_call_log (
                    firm_id, gstin_profile_id, provider, model,
                    attempt, language, succeeded, error_kind,
                    input_tokens, output_tokens,
                    cache_read_input_tokens, cache_creation_input_tokens,
                    latency_ms, cost_paise, pricing_effective_from
                ) VALUES (
                    :fid, :gpid, :prov, :model,
                    :att, :lang, :ok, :ek,
                    :it, :ot, :crt, :cct,
                    :ms, :cp, :pef
                )
                """
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gstin_profile_id),
                "prov": provider,
                "model": model,
                "att": attempt,
                "lang": language,
                "ok": succeeded,
                "ek": error_kind,
                "it": usage.input_tokens,
                "ot": usage.output_tokens,
                "crt": usage.cache_read_input_tokens,
                "cct": usage.cache_creation_input_tokens,
                "ms": int((time.time() - started_at) * 1000),
                "cp": cost_paise,
                "pef": pricing_effective_from,
            },
        )

    # Prometheus counters (Phase 1.6). The counter surface intentionally
    # mirrors the log row: success/hallucination/adapter_error map to
    # narrator_calls_total; cost_paise (when priced) accumulates on
    # narrator_cost_paise_total. Kept last so an increment cannot mask
    # a failed INSERT above.
    from app.observability import metrics

    if cost_paise:
        metrics.narrator_cost_paise_total.labels(model=model).inc(cost_paise)
    outcome = "success" if succeeded else (error_kind or "error")
    metrics.narrator_calls_total.labels(model=model, outcome=outcome).inc()


def _check_pre_call_gates(firm_id: str | uuid.UUID) -> None:
    """Enforce the three pre-call gates in defence-in-depth order.

    Order matters — cheapest check first, so a killed operator flag
    never even reads ``ca_firm``:

    1. ``system_settings.narrator_globally_disabled`` — the runtime
       operator kill-switch. Effective without a deploy. Composes
       with the env-var ``settings.narrator_enabled`` (env is the
       deploy-time base policy; this row hard-offs an incident).
    2. ``ca_firm.narrator_enabled`` — the firm-admin toggle.
    3. ``ca_firm.monthly_narrator_budget_paise`` vs
       ``SUM(cost_paise)`` for the current calendar month. NULL budget
       = no limit. Silent fallback to a cheaper model is disallowed
       (P3_BUILD_PROMPT §3.1.4) so we raise instead of degrading.

    Raises:
      NarratorDisabled — global runtime flag or per-firm flag off.
      NarratorBudgetExhausted — per-firm monthly ceiling reached.

    Executes as three statements inside one firm-scoped transaction so
    the reads see a consistent snapshot; system_settings has no RLS,
    so being firm-scoped does not exclude the row.
    """
    from app.observability import metrics

    with firm_scoped_session(firm_id) as db:
        global_row = db.execute(
            text(
                "SELECT narrator_globally_disabled "
                "FROM system_settings WHERE id = 1"
            )
        ).first()
        if global_row and bool(global_row[0]):
            metrics.narrator_calls_total.labels(
                model="__gate__", outcome="disabled_global"
            ).inc()
            raise NarratorDisabled(
                "narrator globally disabled by operator "
                "(system_settings.narrator_globally_disabled)"
            )
        firm_row = db.execute(
            text(
                "SELECT narrator_enabled, monthly_narrator_budget_paise "
                "FROM ca_firm WHERE id = :id"
            ),
            {"id": str(firm_id)},
        ).first()
        if not firm_row or not bool(firm_row[0]):
            metrics.narrator_calls_total.labels(
                model="__gate__", outcome="disabled_firm"
            ).inc()
            raise NarratorDisabled(
                "narrator disabled for this firm "
                "(firm admin can flip via PATCH /firm/settings)"
            )
        budget = firm_row[1]
        if budget is None:
            return
        # Sum cost_paise for the current calendar month (server clock).
        # Uses the partial index narrator_call_log_firm_month_cost via
        # the WHERE cost_paise IS NOT NULL clause; unpriced rows are
        # correctly excluded so they never eat into the budget.
        used_row = db.execute(
            text(
                """
                SELECT COALESCE(SUM(cost_paise), 0) AS used
                FROM narrator_call_log
                WHERE firm_id = :fid
                  AND cost_paise IS NOT NULL
                  AND EXTRACT(YEAR FROM at) = EXTRACT(YEAR FROM now())
                  AND EXTRACT(MONTH FROM at) = EXTRACT(MONTH FROM now())
                """
            ),
            {"fid": str(firm_id)},
        ).first()
        used = int(used_row[0]) if used_row else 0
        if used >= int(budget):
            metrics.narrator_calls_total.labels(
                model="__gate__", outcome="budget_exhausted"
            ).inc()
            raise NarratorBudgetExhausted(
                used_paise=used, budget_paise=int(budget)
            )


def narrate_for_period(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    return_type: str,
    period: str,
    language: Language,
    user_id: Optional[str | uuid.UUID] = None,
) -> tuple[NarrationOutput, uuid.UUID]:
    """Full flow. Returns the narration + the persisted narration_run id.

    Every adapter invocation (including retries) is recorded to
    ``narrator_call_log`` for cost + cache-hit observability.

    Four independent gates block a call, checked in cheapest-first
    order so a killed operator flag never reaches the LLM plumbing:

      1. ``settings.narrator_enabled`` (env-var; deploy-time base
         policy). Enforced inside :func:`get_adapter`.
      2. ``system_settings.narrator_globally_disabled`` (runtime;
         no-deploy operator kill-switch).
      3. ``ca_firm.narrator_enabled`` (firm-admin toggle).
      4. ``ca_firm.monthly_narrator_budget_paise`` (per-firm monthly
         cost ceiling in paise; NULL = no limit).

    Gates 2–4 are enforced in :func:`_check_pre_call_gates` before
    :func:`get_adapter` so a firm-off / budget-exhausted request never
    touches the LLM plumbing. Gate 1 is checked last (inside
    ``get_adapter``) because the env may be intentionally off in dev.

    Raises:
      NarratorDisabled — env, runtime-global, or per-firm flag off.
      NarratorBudgetExhausted — per-firm monthly ceiling reached
        (a NarratorDisabled subclass so 503 handlers keep working).
      FactsUnavailable — no readiness_snapshot for the triple.
      NumberHallucination — model emitted a bad number twice in a row.
      NarratorError — adapter or SDK failure.
    """
    _check_pre_call_gates(firm_id)
    adapter = get_adapter()  # may raise NarratorDisabled (env-var gate)
    with firm_scoped_session(firm_id) as db:
        facts = build_facts(
            db,
            firm_id=firm_id,
            gstin_profile_id=gstin_profile_id,
            return_type=return_type,
            period=period,
        )

    retried = False

    # First attempt. Wrap in try so an adapter-level exception (API
    # error, JSON parse failure) is logged before it propagates.
    started = time.time()
    try:
        output = _call_adapter(adapter, facts, language, strict=False)
    except NarratorError:
        _log_call(
            firm_id=firm_id,
            gstin_profile_id=gstin_profile_id,
            provider=adapter.provider,
            model=adapter.model,
            attempt=1,
            language=language,
            succeeded=False,
            error_kind="adapter_error",
            usage=TokenUsage(),
            started_at=started,
        )
        raise

    try:
        validator.validate_output_blocks(facts=facts, blocks=_to_blocks(output))
    except NumberHallucination as first_err:
        log.warning(
            "narrator.hallucination attempt=1 provider=%s offending=%s",
            output.provider,
            first_err.offending,
        )
        _log_call(
            firm_id=firm_id,
            gstin_profile_id=gstin_profile_id,
            provider=output.provider,
            model=output.model,
            attempt=1,
            language=language,
            succeeded=False,
            error_kind="hallucination",
            usage=output.usage,
            started_at=started,
        )
        # Retry once with a stricter reminder.
        retried = True
        started = time.time()
        try:
            output = _call_adapter(adapter, facts, language, strict=True)
        except NarratorError:
            _log_call(
                firm_id=firm_id,
                gstin_profile_id=gstin_profile_id,
                provider=adapter.provider,
                model=adapter.model,
                attempt=2,
                language=language,
                succeeded=False,
                error_kind="adapter_error",
                usage=TokenUsage(),
                started_at=started,
            )
            raise
        try:
            validator.validate_output_blocks(
                facts=facts, blocks=_to_blocks(output)
            )
        except NumberHallucination as second_err:
            log.error(
                "narrator.hallucination attempt=2 provider=%s offending=%s",
                output.provider,
                second_err.offending,
            )
            _log_call(
                firm_id=firm_id,
                gstin_profile_id=gstin_profile_id,
                provider=output.provider,
                model=output.model,
                attempt=2,
                language=language,
                succeeded=False,
                error_kind="hallucination",
                usage=output.usage,
                started_at=started,
            )
            raise

    # Successful attempt.
    _log_call(
        firm_id=firm_id,
        gstin_profile_id=gstin_profile_id,
        provider=output.provider,
        model=output.model,
        attempt=2 if retried else 1,
        language=language,
        succeeded=True,
        error_kind=None,
        usage=output.usage,
        started_at=started,
    )

    run_id = _persist_run(
        firm_id=firm_id,
        gstin_profile_id=gstin_profile_id,
        return_type=return_type,
        period=period,
        language=language,
        facts=facts,
        output=output,
        generated_by=user_id,
    )
    return output, run_id


# ---------------------------------------------------------------------------
# Cost + cache-hit meter
# ---------------------------------------------------------------------------
# Pricing itself lives in :mod:`app.narrator.pricing` (Phase 1.4).
# ``cost_paise`` is written at call time by :func:`_log_call`; the
# aggregation below reads it directly from ``narrator_call_log`` and
# never recomputes cost after the fact — that would let a pricing-
# table update rewrite historical cost totals.


def monthly_narrator_stats(
    *, firm_id: str | uuid.UUID, month: str
) -> dict:
    """Aggregate ``narrator_call_log`` rows for the firm in ``month`` (YYYYMM).

    Returns a JSON-safe dict with:

    ``total_calls`` — every logged call (attempts + retries + failures).
    ``succeeded`` / ``failed`` — split by ``succeeded`` column.
    ``failures_by_kind`` — count per error_kind (hallucination,
        adapter_error, ...).
    ``input_tokens`` — sum. NULL rows (mock adapter) count as 0.
    ``output_tokens`` — sum.
    ``cache_read_input_tokens`` — sum. Drives cache-hit rate.
    ``cache_creation_input_tokens`` — sum.
    ``cache_hit_rate`` — cache_read / (cache_read + cache_creation + fresh input)
        expressed as a percentage 0.0–100.0. None if no input tokens seen at
        all (mock-only month). Load-bearing metric for Step 4 — the P2.4
        goal is "~90% cache-read on regenerations."
    ``per_model`` — list of ``{model, calls, input_tokens, output_tokens,
        cache_read_input_tokens, cache_creation_input_tokens,
        cost_paise, unpriced_calls}`` rows. ``cost_paise`` is the sum of
        the ``narrator_call_log.cost_paise`` column for that model in
        the window; NULL rows (unpriced model, or mock adapter with no
        tokens) are excluded from the sum and counted in
        ``unpriced_calls`` instead. A per_model row with all-unpriced
        calls has ``cost_paise = 0`` and ``unpriced_calls = calls``.
    ``cost_paise`` — sum across all models in the window. Excludes
        unpriced rows.
    ``any_unpriced`` — True if any priced-succeeded call in the window
        had ``cost_paise IS NULL`` (unknown model). The dashboard
        surfaces this so the CA cannot misread a partial total as the
        real bill.
    ``latency_ms_p50`` / ``latency_ms_p95`` — median + 95th percentile
        across all logged calls. Uses percentile_cont, so approximate on
        small samples but the right shape for cost dashboards.
    """
    if len(month) != 6 or not month.isdigit():
        raise ValueError("month must be YYYYMM")
    year, mm = int(month[:4]), int(month[4:])
    if not 1 <= mm <= 12:
        raise ValueError(f"month must be YYYYMM with a real month; got {month!r}")

    with firm_scoped_session(firm_id) as db:
        totals_row = db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_calls,
                    COUNT(*) FILTER (WHERE succeeded) AS succeeded,
                    COUNT(*) FILTER (WHERE NOT succeeded) AS failed,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(cache_read_input_tokens), 0)
                        AS cache_read_input_tokens,
                    COALESCE(SUM(cache_creation_input_tokens), 0)
                        AS cache_creation_input_tokens,
                    percentile_cont(0.5)
                        WITHIN GROUP (ORDER BY latency_ms) AS latency_ms_p50,
                    percentile_cont(0.95)
                        WITHIN GROUP (ORDER BY latency_ms) AS latency_ms_p95
                FROM narrator_call_log
                WHERE firm_id = :fid
                  AND EXTRACT(YEAR FROM at) = :y
                  AND EXTRACT(MONTH FROM at) = :m
                """
            ),
            {"fid": str(firm_id), "y": year, "m": mm},
        ).mappings().one()

        failures_by_kind_rows = db.execute(
            text(
                """
                SELECT error_kind, COUNT(*) AS n
                FROM narrator_call_log
                WHERE firm_id = :fid
                  AND EXTRACT(YEAR FROM at) = :y
                  AND EXTRACT(MONTH FROM at) = :m
                  AND NOT succeeded
                  AND error_kind IS NOT NULL
                GROUP BY error_kind
                ORDER BY n DESC
                """
            ),
            {"fid": str(firm_id), "y": year, "m": mm},
        ).mappings().all()

        # Per-model aggregation. ``cost_paise`` sums the column
        # written at call time so a later pricing-table update never
        # rewrites historical cost totals. Unpriced rows (cost_paise
        # IS NULL) are counted separately so the dashboard can flag a
        # partial total honestly.
        per_model_rows = db.execute(
            text(
                """
                SELECT
                    model,
                    COUNT(*) AS calls,
                    COUNT(*) FILTER (
                        WHERE succeeded
                          AND cost_paise IS NULL
                          AND input_tokens IS NOT NULL
                    ) AS unpriced_calls,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(cache_read_input_tokens), 0)
                        AS cache_read_input_tokens,
                    COALESCE(SUM(cache_creation_input_tokens), 0)
                        AS cache_creation_input_tokens,
                    COALESCE(SUM(cost_paise), 0) AS cost_paise
                FROM narrator_call_log
                WHERE firm_id = :fid
                  AND EXTRACT(YEAR FROM at) = :y
                  AND EXTRACT(MONTH FROM at) = :m
                GROUP BY model
                ORDER BY model
                """
            ),
            {"fid": str(firm_id), "y": year, "m": mm},
        ).mappings().all()

    # Cache-hit rate: cache_read / total input the model actually saw.
    total_input_seen = (
        int(totals_row["input_tokens"])
        + int(totals_row["cache_read_input_tokens"])
        # NB: input_tokens on Anthropic responses is "fresh input"; the
        # cache_read and cache_creation are reported separately. Total
        # input the model processed = input_tokens + cache_read + cache_creation.
        # We treat cache_creation as counting toward "hit" because it
        # is priced closer to fresh input than to a hit — treat that
        # separately in the dashboard if it becomes material.
        + int(totals_row["cache_creation_input_tokens"])
    )
    if total_input_seen > 0:
        cache_hit_rate = round(
            100.0 * int(totals_row["cache_read_input_tokens"]) / total_input_seen,
            2,
        )
    else:
        cache_hit_rate = None

    per_model: list[dict] = []
    total_cost_paise = 0
    any_unpriced = False
    for r in per_model_rows:
        unpriced = int(r["unpriced_calls"])
        if unpriced > 0:
            any_unpriced = True
        total_cost_paise += int(r["cost_paise"])
        per_model.append(
            {
                "model": r["model"],
                "calls": int(r["calls"]),
                "input_tokens": int(r["input_tokens"]),
                "output_tokens": int(r["output_tokens"]),
                "cache_read_input_tokens": int(r["cache_read_input_tokens"]),
                "cache_creation_input_tokens": int(
                    r["cache_creation_input_tokens"]
                ),
                "cost_paise": int(r["cost_paise"]),
                "unpriced_calls": unpriced,
            }
        )

    return {
        "firm_id": str(firm_id),
        "month": month,
        "total_calls": int(totals_row["total_calls"]),
        "succeeded": int(totals_row["succeeded"]),
        "failed": int(totals_row["failed"]),
        "failures_by_kind": {
            r["error_kind"]: int(r["n"]) for r in failures_by_kind_rows
        },
        "input_tokens": int(totals_row["input_tokens"]),
        "output_tokens": int(totals_row["output_tokens"]),
        "cache_read_input_tokens": int(totals_row["cache_read_input_tokens"]),
        "cache_creation_input_tokens": int(
            totals_row["cache_creation_input_tokens"]
        ),
        "cache_hit_rate": cache_hit_rate,
        "per_model": per_model,
        "cost_paise": total_cost_paise,
        "any_unpriced": any_unpriced,
        "pricing_effective_from": pricing.PRICING_EFFECTIVE_FROM.isoformat(),
        "latency_ms_p50": (
            float(totals_row["latency_ms_p50"])
            if totals_row["latency_ms_p50"] is not None
            else None
        ),
        "latency_ms_p95": (
            float(totals_row["latency_ms_p95"])
            if totals_row["latency_ms_p95"] is not None
            else None
        ),
    }
