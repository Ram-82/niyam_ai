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
from app.narrator import validator
from app.narrator.facts_builder import FactsUnavailable, build_facts
from app.narrator.mock_adapter import MockNarrator
from app.narrator.types import (
    Language,
    Narrator,
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
    with firm_scoped_session(firm_id) as db:
        db.execute(
            text(
                """
                INSERT INTO narrator_call_log (
                    firm_id, gstin_profile_id, provider, model,
                    attempt, language, succeeded, error_kind,
                    input_tokens, output_tokens,
                    cache_read_input_tokens, cache_creation_input_tokens,
                    latency_ms
                ) VALUES (
                    :fid, :gpid, :prov, :model,
                    :att, :lang, :ok, :ek,
                    :it, :ot, :crt, :cct,
                    :ms
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
            },
        )


def _firm_narrator_enabled(firm_id: str | uuid.UUID) -> bool:
    """Read the per-firm ``ca_firm.narrator_enabled`` flag.

    Returns False if the row is missing (defensive — should never
    happen inside a firm-scoped call, but a False here just means
    we raise NarratorDisabled rather than crashing).
    """
    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text("SELECT narrator_enabled FROM ca_firm WHERE id = :id"),
            {"id": str(firm_id)},
        ).first()
    return bool(row and row[0])


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

    Two independent gates block a call:
      1. The global ``settings.narrator_enabled`` (operator kill switch).
         Enforced inside :func:`get_adapter`.
      2. The per-firm ``ca_firm.narrator_enabled`` (firm-admin toggle).
         Enforced here, checked BEFORE invoking ``get_adapter`` so a
         firm-off request never touches the LLM plumbing.

    Both must be true for a call to fire. Either being false raises
    ``NarratorDisabled``. The distinction between the two is invisible
    to the CA — the API returns 503 either way.

    Raises:
      NarratorDisabled — global OR per-firm flag off.
      FactsUnavailable — no readiness_snapshot for the triple.
      NumberHallucination — model emitted a bad number twice in a row.
      NarratorError — adapter or SDK failure.
    """
    if not _firm_narrator_enabled(firm_id):
        raise NarratorDisabled(
            "narrator disabled for this firm "
            "(firm admin can flip via PATCH /firm/settings)"
        )
    adapter = get_adapter()  # may raise NarratorDisabled (global flag)
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
# Cost + cache-hit meter (P2.4 Step 3)
# ---------------------------------------------------------------------------


# Provider list prices in USD per million tokens. Kept as module-level
# constants so a price update is a one-line change and the operator can
# grep for "PRICE_USD_PER_M" to find them. If we swap in another model
# id, add a new dict entry keyed by the model id string.
#
# Source: provider pricing pages as of 2026-08. Update on any
# announced price change — the estimate we return to the admin is a
# best-effort forward-look, not a billed figure.
_MODEL_PRICE_USD_PER_M: dict[str, dict[str, float]] = {
    # Anthropic Opus 4.7
    "claude-opus-4-7": {
        "input": 15.00,
        "output": 75.00,
        # Cache read is 10x cheaper than fresh input.
        "cache_read": 1.50,
        # Cache creation is a one-time cost, ~25% premium over fresh input.
        "cache_creation": 18.75,
    },
    # Anthropic Sonnet 4.6
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    # Anthropic Haiku 4.5 — current default (settings.narrator_model)
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_creation": 1.25,
    },
    # Google Gemini 2.5 Flash — cheapest workable option for the
    # narrator task. Free tier available with different privacy terms
    # (see docs/narrator-security.md §Provider policies).
    "gemini-2.5-flash": {
        "input": 0.35,
        "output": 1.05,
        # Gemini caching is opt-in via CachedContent objects and not
        # wired in the current adapter. Set the cache prices anyway so
        # a future caching-enabled build gets accurate numbers.
        "cache_read": 0.09,
        "cache_creation": 1.00,
    },
    # Google Gemini 2.5 Pro — higher quality vernacular, still cheap
    "gemini-2.5-pro": {
        "input": 1.25,
        "output": 5.00,
        "cache_read": 0.31,
        "cache_creation": 1.25,
    },
}


# Old name kept as an alias for any external caller that grepped the
# module-level constant. Delete after one release cycle.
_ANTHROPIC_PRICE_USD_PER_M = _MODEL_PRICE_USD_PER_M


def _estimate_usd(model: str, usage: dict) -> Optional[float]:
    """Best-effort USD estimate. None if model not in the price table.

    We NULL rather than assume a default price so a dashboard shows
    "unpriced model" loudly rather than a wrong number silently.
    """
    prices = _MODEL_PRICE_USD_PER_M.get(model)
    if prices is None:
        return None
    it = usage.get("input_tokens") or 0
    ot = usage.get("output_tokens") or 0
    crt = usage.get("cache_read_input_tokens") or 0
    cct = usage.get("cache_creation_input_tokens") or 0
    # Fresh input tokens = input_tokens - cache_read - cache_creation
    # (Anthropic reports these as disjoint counts; sum of all three is
    # the total input the model processed.)
    fresh_input = max(0, it - crt - cct)
    total_micro = (
        fresh_input * prices["input"]
        + ot * prices["output"]
        + crt * prices["cache_read"]
        + cct * prices["cache_creation"]
    )
    return round(total_micro / 1_000_000, 6)


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
        estimated_usd}`` rows. Priced only for models in
        ``_ANTHROPIC_PRICE_USD_PER_M``; unknown models return
        ``estimated_usd=None`` so the dashboard flags them.
    ``estimated_usd`` — sum of per_model estimates; None if ANY model
        row was unpriced (so the admin can't misread partial data as
        the total).
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

        per_model_rows = db.execute(
            text(
                """
                SELECT
                    model,
                    COUNT(*) AS calls,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(cache_read_input_tokens), 0)
                        AS cache_read_input_tokens,
                    COALESCE(SUM(cache_creation_input_tokens), 0)
                        AS cache_creation_input_tokens
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
    any_unpriced = False
    total_usd = 0.0
    for r in per_model_rows:
        usage_dict = {
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "cache_read_input_tokens": r["cache_read_input_tokens"],
            "cache_creation_input_tokens": r["cache_creation_input_tokens"],
        }
        usd = _estimate_usd(r["model"], usage_dict)
        if usd is None:
            any_unpriced = True
        else:
            total_usd += usd
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
                "estimated_usd": usd,
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
        "estimated_usd": None if any_unpriced else round(total_usd, 6),
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
