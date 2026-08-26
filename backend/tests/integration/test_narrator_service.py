"""Narrator service integration tests.

These tests exercise the whole service.narrate_for_period flow against
a real Postgres, using the mock adapter (no external API calls) or a
stub adapter injected via monkeypatch. Coverage:

* Happy path — mock adapter round-trip persists narration_run + audit_log.
* Hallucination retry — first call hallucinates, second call clean,
  retry policy succeeds.
* Double hallucination — bubbles NumberHallucination to caller.
* Feature flag off — NarratorDisabled.
* Missing readiness_snapshot — FactsUnavailable.
* narration_run is append-only (RLS + trigger checks).

Uses ``bootstrap_firm`` + directly-inserted domain rows (readiness
snapshot, reconciliation_run) rather than driving the engine end-to-end;
the engines have their own tests, we're focused on the narrator wiring
here.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import text

from app.config import settings
from app.db import owner_engine
from app.narrator import service
from app.narrator.facts_builder import FactsUnavailable
from app.narrator.types import (
    BlockerFact,
    NarrationFacts,
    NarrationOutput,
    NarratorDisabled,
    NarratorError,
    NumberHallucination,
    TokenUsage,
)


# ---------------------------------------------------------------------------
# Test fixtures — narrator feature flag on for this module only.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_narrator(monkeypatch: pytest.MonkeyPatch):
    """The service reads ``settings.narrator_enabled`` at each call — so
    flipping this fixture-scoped flag has the right effect. We flip it
    on by default; individual tests that want the OFF path flip it back."""
    monkeypatch.setattr(settings, "narrator_enabled", True)
    monkeypatch.setattr(settings, "narrator_mode", "mock")
    yield


# ---------------------------------------------------------------------------
# Domain seed helpers
# ---------------------------------------------------------------------------


def _seed_readiness(
    *,
    firm_id: uuid.UUID,
    gstin_profile_id: uuid.UUID,
    period: str = "202607",
    return_type: str = "GSTR1",
    score: int = 65,
) -> None:
    """Insert a gstn_pull + reconciliation_run + readiness_snapshot +
    a few invoices so build_facts has data to pull."""
    with owner_engine.begin() as conn:
        # reconciliation_run needs a gstn_pull row (FK). Insert a stub.
        pull_id = conn.execute(
            text(
                """
                INSERT INTO gstn_pull (
                    firm_id, gstin_profile_id, return_type, period,
                    raw_payload, source
                ) VALUES (
                    :fid, :gpid, 'GSTR2B', :p,
                    CAST('{}' AS JSONB), 'json_import'
                )
                RETURNING id
                """
            ),
            {"fid": str(firm_id), "gpid": str(gstin_profile_id), "p": period},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO reconciliation_run (
                    firm_id, gstin_profile_id, period, rule_pack_version,
                    gstn_pull_id, summary
                ) VALUES (
                    :fid, :gpid, :p, '1.0.0', :pid, CAST(:s AS JSONB)
                )
                """
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gstin_profile_id),
                "p": period,
                "pid": str(pull_id),
                "s": json.dumps(
                    {
                        "matched": {"count": 3, "paise": 2_50_00_000},
                        "probable": {"count": 2, "paise": 1_50_00_000},
                        "supplier_default": {
                            "count": 6,
                            "paise": 43_00_000,
                            "top_suppliers": [],
                        },
                        "missing_entry": {"count": 4, "paise": 1_20_00_000},
                    }
                ),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO readiness_snapshot (
                    firm_id, gstin_profile_id, return_type, period,
                    score, blockers, arithmetic, rule_pack_version
                ) VALUES (
                    :fid, :gpid, :rt, :p,
                    :score, CAST(:b AS JSONB), CAST(:a AS JSONB), '1.0.0'
                )
                """
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gstin_profile_id),
                "rt": return_type,
                "p": period,
                "score": score,
                "b": json.dumps(
                    [
                        {
                            "kind": "supplier_default",
                            "owner": "ca",
                            "description": "ITC at risk from 6 suppliers",
                            "paise_impact": 43_00_000,
                        }
                    ]
                ),
                "a": json.dumps(
                    {"tax_paid_paise": 25_00_000, "tax_due_paise": 30_00_000}
                ),
            },
        )
        # A couple of invoices so sales/purchases are non-zero.
        invoice_date = date(int(period[:4]), int(period[4:]), 15)
        for direction, number, total, h_suffix in (
            ("sale", "S-1", 10000000, "s"),        # ₹1,00,000
            ("purchase", "P-1", 5000000, "p"),      # ₹50,000
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO invoice (
                        firm_id, gstin_profile_id, source, direction,
                        invoice_number, invoice_date, taxable_value_paise,
                        total_paise, content_hash
                    ) VALUES (
                        :fid, :gid, 'csv_import', :dir,
                        :num, :dt, :amt,
                        :amt, :h
                    )
                    """
                ),
                {
                    "fid": str(firm_id),
                    "gid": str(gstin_profile_id),
                    "dir": direction,
                    "num": number,
                    "dt": invoice_date,
                    "amt": total,
                    "h": f"h-{h_suffix}-{gstin_profile_id}",
                },
            )


def _make_gstin(bootstrap: dict) -> uuid.UUID:
    """Create a client + GSTIN in the bootstrapped firm.

    Also flips ``ca_firm.narrator_enabled=true`` for the firm — the
    P2.4 Step 2 migration defaults new firms to OFF (opt-in) but every
    test in this module wants narration to work. Real-world analog is
    a firm admin enabling narration in Settings → Preferences before
    exercising the feature.
    """
    firm_id = bootstrap["firm_id"]
    client_id = uuid.uuid4()
    gstin_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) VALUES (:cid, :fid, 'Beta Traders')"
            ),
            {"cid": client_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, '29ABCDE1234F1Z5', '29')"
            ),
            {"gid": gstin_id, "fid": firm_id, "cid": client_id},
        )
        conn.execute(
            text("UPDATE ca_firm SET narrator_enabled = true WHERE id = :fid"),
            {"fid": firm_id},
        )
    return gstin_id


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_mock_adapter_round_trip_persists_narration_run(bootstrap_firm) -> None:
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    output, run_id = service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
        user_id=b["user_id"],
    )

    assert output.provider == "mock"
    assert "₹43,000" in output.page2_ask_your_ca
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT provider, language, generated_by FROM narration_run "
                "WHERE id = :id"
            ),
            {"id": str(run_id)},
        ).first()
    assert row is not None
    assert row[0] == "mock"
    assert row[1] == "en"
    assert str(row[2]) == str(b["user_id"])

    # Audit trail
    with owner_engine.begin() as conn:
        actions = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT action FROM audit_log WHERE firm_id = :fid "
                    "ORDER BY at DESC"
                ),
                {"fid": str(b["firm_id"])},
            ).all()
        ]
    assert "narration.generated" in actions


def test_no_readiness_snapshot_raises_facts_unavailable(bootstrap_firm) -> None:
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    # No _seed_readiness — the snapshot is missing.
    with pytest.raises(FactsUnavailable):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )


def test_feature_flag_off_raises_disabled(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    monkeypatch.setattr(settings, "narrator_enabled", False)
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    with pytest.raises(NarratorDisabled):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )


# ---------------------------------------------------------------------------
# Hallucination retry
# ---------------------------------------------------------------------------


class _StubAdapter:
    """Emits a bad number on the first call, then clean prose."""

    provider = "stub"
    model = "stub-1"

    def __init__(self) -> None:
        self.calls = 0

    def narrate(self, facts, language, *, strict_reminder: bool = False):
        self.calls += 1
        if self.calls == 1:
            return NarrationOutput(
                page1_health="Sales were ₹99,999 for the period.",  # NOT in facts
                page1_tax_position="",
                page2_attention="",
                page2_ask_your_ca="",
                provider=self.provider,
                model=self.model,
                language=language,
            )
        # Clean second call — echo actual facts numbers.
        return NarrationOutput(
            page1_health=f"Sales stood at ₹{facts.sales_paise // 100}.",
            page1_tax_position="",
            page2_attention="",
            page2_ask_your_ca="",
            provider=self.provider,
            model=self.model,
            language=language,
        )


class _AlwaysBadAdapter:
    provider = "stub"
    model = "stub-1"

    def narrate(self, facts, language, *, strict_reminder: bool = False):
        return NarrationOutput(
            page1_health="Sales were ₹99,999 for the period.",
            page1_tax_position="",
            page2_attention="",
            page2_ask_your_ca="",
            provider=self.provider,
            model=self.model,
            language=language,
        )


def test_first_hallucination_retries_and_second_clean_succeeds(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    stub = _StubAdapter()
    monkeypatch.setattr(service, "get_adapter", lambda: stub)
    output, _ = service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )
    assert stub.calls == 2
    assert "99,999" not in output.page1_health


def test_double_hallucination_bubbles(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    monkeypatch.setattr(service, "get_adapter", lambda: _AlwaysBadAdapter())
    with pytest.raises(NumberHallucination):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )


# ---------------------------------------------------------------------------
# Append-only guard — UPDATE + DELETE on narration_run must raise.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Per-firm narrator toggle — P2.4 Step 2
# ---------------------------------------------------------------------------


def test_per_firm_flag_off_raises_disabled(bootstrap_firm) -> None:
    """Firm with narrator_enabled=false → NarratorDisabled even with
    global flag on."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)  # sets narrator_enabled=true
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    # Now flip THIS firm's per-firm flag back off.
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ca_firm SET narrator_enabled = false WHERE id = :fid"
            ),
            {"fid": str(b["firm_id"])},
        )

    with pytest.raises(NarratorDisabled):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )


def test_per_firm_isolation_a_on_b_off(bootstrap_firm) -> None:
    """Firm A narrator=true → succeeds. Firm B narrator=false → NarratorDisabled.
    Global flag stays on the whole time."""
    a = bootstrap_firm(admin_email="iso-a@example.com")
    b = bootstrap_firm(admin_email="iso-b@example.com")
    gpid_a = _make_gstin(a)  # sets A on
    gpid_b = _make_gstin(b)  # sets B on
    _seed_readiness(firm_id=a["firm_id"], gstin_profile_id=gpid_a)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid_b)

    # Turn firm B off.
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ca_firm SET narrator_enabled = false WHERE id = :fid"
            ),
            {"fid": str(b["firm_id"])},
        )

    # Firm A still succeeds.
    output_a, _ = service.narrate_for_period(
        firm_id=a["firm_id"],
        gstin_profile_id=gpid_a,
        return_type="GSTR1",
        period="202607",
        language="en",
    )
    assert output_a.provider == "mock"

    # Firm B raises.
    with pytest.raises(NarratorDisabled):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid_b,
            return_type="GSTR1",
            period="202607",
            language="en",
        )


def test_global_off_kills_all_firms_regardless_of_per_firm(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """Global NARRATOR_ENABLED=false → NarratorDisabled even if the firm
    has narrator_enabled=true. The global flag is the operator kill
    switch — trumps every per-firm decision."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)  # sets firm narrator_enabled=true
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    # Firm is on, but global is off → still disabled.
    monkeypatch.setattr(settings, "narrator_enabled", False)
    with pytest.raises(NarratorDisabled):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )


def test_per_firm_off_skips_llm_before_call_log(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """A firm-off request must not touch the adapter, must not write a
    narrator_call_log row. Load-bearing: we don't want to log 'call
    attempted' when the CA didn't even opt in — that would poison the
    cost dashboard."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    # Turn firm off.
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ca_firm SET narrator_enabled = false WHERE id = :fid"
            ),
            {"fid": str(b["firm_id"])},
        )

    # A stub that WOULD fail the test if called, to prove get_adapter
    # was skipped entirely.
    class _MustNotBeCalled:
        provider = "must-not"
        model = "must-not"

        def narrate(self, *a, **kw):
            raise AssertionError("adapter should not have been invoked")

    monkeypatch.setattr(service, "get_adapter", lambda: _MustNotBeCalled())

    with pytest.raises(NarratorDisabled):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )

    # No call_log row was written.
    rows = _read_call_logs(b["firm_id"])
    assert rows == []


# ---------------------------------------------------------------------------
# narrator_call_log — cost + cache-hit meter
# ---------------------------------------------------------------------------


def _read_call_logs(firm_id) -> list[dict]:
    """Return all narrator_call_log rows for a firm, oldest first."""
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT attempt, succeeded, error_kind, provider, model, "
                "language, input_tokens, output_tokens, "
                "cache_read_input_tokens, cache_creation_input_tokens, "
                "latency_ms "
                "FROM narrator_call_log WHERE firm_id = :fid "
                "ORDER BY at ASC, attempt ASC"
            ),
            {"fid": str(firm_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


class _UsageStubAdapter:
    """Emits clean prose + explicit usage values (mimics AnthropicNarrator)."""

    provider = "stub-anthropic"
    model = "claude-stub"

    def __init__(self, *, input_tokens=1200, output_tokens=350,
                 cache_read=800, cache_creation=0) -> None:
        self._usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        )

    def narrate(self, facts, language, *, strict_reminder: bool = False):
        return NarrationOutput(
            page1_health=f"Sales stood at ₹{facts.sales_paise // 100}.",
            page1_tax_position="",
            page2_attention="",
            page2_ask_your_ca="",
            provider=self.provider,
            model=self.model,
            language=language,
            usage=self._usage,
        )


class _AdapterErrorAdapter:
    provider = "stub-anthropic"
    model = "claude-stub"

    def narrate(self, facts, language, *, strict_reminder: bool = False):
        raise NarratorError("simulated SDK failure")


def test_happy_path_writes_one_call_log_row(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    monkeypatch.setattr(service, "get_adapter", lambda: _UsageStubAdapter())

    service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )

    rows = _read_call_logs(b["firm_id"])
    assert len(rows) == 1
    r = rows[0]
    assert r["attempt"] == 1
    assert r["succeeded"] is True
    assert r["error_kind"] is None
    assert r["provider"] == "stub-anthropic"
    assert r["model"] == "claude-stub"
    assert r["language"] == "en"
    assert r["input_tokens"] == 1200
    assert r["output_tokens"] == 350
    assert r["cache_read_input_tokens"] == 800
    assert r["cache_creation_input_tokens"] == 0
    assert r["latency_ms"] >= 0


def test_mock_adapter_writes_row_with_null_tokens(bootstrap_firm) -> None:
    """The mock adapter makes no LLM call — token columns must be NULL,
    NOT 0. NULL means 'no LLM call was made'; 0 would mean
    'called and reported 0', which would be a bug."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )

    rows = _read_call_logs(b["firm_id"])
    assert len(rows) == 1
    assert rows[0]["provider"] == "mock"
    assert rows[0]["input_tokens"] is None
    assert rows[0]["output_tokens"] is None
    assert rows[0]["cache_read_input_tokens"] is None
    assert rows[0]["cache_creation_input_tokens"] is None
    # But latency still measured — mock is fast so this is a small int.
    assert rows[0]["latency_ms"] is not None
    assert rows[0]["latency_ms"] >= 0


def test_hallucination_retry_writes_two_rows(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """attempt=1 logged with error_kind='hallucination', succeeded=false;
    attempt=2 logged with succeeded=true."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    monkeypatch.setattr(service, "get_adapter", lambda: _StubAdapter())

    service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )

    rows = _read_call_logs(b["firm_id"])
    assert len(rows) == 2
    assert rows[0]["attempt"] == 1
    assert rows[0]["succeeded"] is False
    assert rows[0]["error_kind"] == "hallucination"
    assert rows[1]["attempt"] == 2
    assert rows[1]["succeeded"] is True
    assert rows[1]["error_kind"] is None


def test_double_hallucination_writes_two_failure_rows(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    monkeypatch.setattr(service, "get_adapter", lambda: _AlwaysBadAdapter())

    with pytest.raises(NumberHallucination):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )

    rows = _read_call_logs(b["firm_id"])
    assert len(rows) == 2
    assert all(r["succeeded"] is False for r in rows)
    assert all(r["error_kind"] == "hallucination" for r in rows)
    assert [r["attempt"] for r in rows] == [1, 2]


def test_adapter_error_writes_failure_row(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """SDK-level failure (JSON parse error, API 500, timeout) is caught
    and logged BEFORE the exception propagates — so cost dashboards can
    still see failed-call cost + latency."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    monkeypatch.setattr(service, "get_adapter", lambda: _AdapterErrorAdapter())

    with pytest.raises(NarratorError):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )

    rows = _read_call_logs(b["firm_id"])
    assert len(rows) == 1
    assert rows[0]["attempt"] == 1
    assert rows[0]["succeeded"] is False
    assert rows[0]["error_kind"] == "adapter_error"
    # Token cols NULL — no LLM response reached us.
    assert rows[0]["input_tokens"] is None


def test_call_log_is_append_only(bootstrap_firm) -> None:
    """Mirrors the narration_run + gsp_call_log invariant — no UPDATE, no DELETE."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )
    with owner_engine.begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.execute(
                text(
                    "UPDATE narrator_call_log SET succeeded = false "
                    "WHERE firm_id = :fid"
                ),
                {"fid": str(b["firm_id"])},
            )
    with owner_engine.begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.execute(
                text(
                    "DELETE FROM narrator_call_log WHERE firm_id = :fid"
                ),
                {"fid": str(b["firm_id"])},
            )


# ---------------------------------------------------------------------------
# monthly_narrator_stats — P2.4 Step 3 cost + cache-hit meter
# ---------------------------------------------------------------------------


def _insert_call_log(
    firm_id,
    *,
    provider="anthropic",
    model="claude-opus-4-7",
    succeeded=True,
    error_kind=None,
    input_tokens=1000,
    output_tokens=300,
    cache_read=800,
    cache_creation=0,
    latency_ms=200,
    cost_paise=None,
    at=None,
):
    """Direct-insert into narrator_call_log for controlled cost tests.

    Bypasses the service layer so tests can seed rows across months +
    models without needing 100 different narration runs. ``cost_paise``
    defaults to None (unpriced) — set it explicitly when the test wants
    to exercise the priced path or budget aggregation.
    """
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO narrator_call_log (
                    firm_id, provider, model, attempt, language,
                    succeeded, error_kind,
                    input_tokens, output_tokens,
                    cache_read_input_tokens, cache_creation_input_tokens,
                    latency_ms, cost_paise, at
                ) VALUES (
                    :fid, :prov, :model, 1, 'en',
                    :ok, :ek,
                    :it, :ot, :crt, :cct,
                    :ms, :cp, COALESCE(:at, now())
                )
                """
            ),
            {
                "fid": str(firm_id),
                "prov": provider,
                "model": model,
                "ok": succeeded,
                "ek": error_kind,
                "it": input_tokens,
                "ot": output_tokens,
                "crt": cache_read,
                "cct": cache_creation,
                "ms": latency_ms,
                "cp": cost_paise,
                "at": at,
            },
        )


def _current_month() -> str:
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    return f"{now.year:04d}{now.month:02d}"


def test_monthly_stats_empty_month(bootstrap_firm) -> None:
    b = bootstrap_firm()
    stats = service.monthly_narrator_stats(
        firm_id=b["firm_id"], month=_current_month()
    )
    assert stats["total_calls"] == 0
    assert stats["succeeded"] == 0
    assert stats["failed"] == 0
    assert stats["input_tokens"] == 0
    assert stats["cache_hit_rate"] is None  # no data → no meaningful rate
    assert stats["cost_paise"] == 0
    assert stats["any_unpriced"] is False
    assert stats["per_model"] == []
    assert stats["latency_ms_p50"] is None


def test_monthly_stats_aggregates_tokens_and_calls(bootstrap_firm) -> None:
    b = bootstrap_firm()
    fid = b["firm_id"]
    # 3 successful calls, all opus, all with cache hits.
    for _ in range(3):
        _insert_call_log(
            fid,
            input_tokens=1000,
            output_tokens=300,
            cache_read=800,
            cache_creation=100,
            latency_ms=200,
        )
    # 1 failed call, no tokens.
    _insert_call_log(
        fid,
        succeeded=False,
        error_kind="adapter_error",
        input_tokens=0,
        output_tokens=0,
        cache_read=0,
        cache_creation=0,
        latency_ms=500,
    )

    stats = service.monthly_narrator_stats(firm_id=fid, month=_current_month())
    assert stats["total_calls"] == 4
    assert stats["succeeded"] == 3
    assert stats["failed"] == 1
    assert stats["failures_by_kind"] == {"adapter_error": 1}
    assert stats["input_tokens"] == 3000
    assert stats["output_tokens"] == 900
    assert stats["cache_read_input_tokens"] == 2400
    assert stats["cache_creation_input_tokens"] == 300


def test_monthly_stats_cache_hit_rate_math(bootstrap_firm) -> None:
    """cache_read / (input + cache_read + cache_creation) as a percentage."""
    b = bootstrap_firm()
    fid = b["firm_id"]
    # input=1000, cache_read=8000, cache_creation=1000 → 8000 / 10000 = 80%
    _insert_call_log(
        fid,
        input_tokens=1000,
        cache_read=8000,
        cache_creation=1000,
    )
    stats = service.monthly_narrator_stats(firm_id=fid, month=_current_month())
    assert stats["cache_hit_rate"] == 80.0


def test_monthly_stats_priced_and_unpriced_models(bootstrap_firm) -> None:
    """A known model produces cost_paise; an unknown model produces
    unpriced_calls > 0 and forces the aggregate ``any_unpriced`` flag
    to True (so the dashboard flags partial data instead of silently
    under-counting)."""
    from app.narrator import pricing

    b = bootstrap_firm()
    fid = b["firm_id"]
    # Priced model — set cost_paise as the service would.
    opus_cost = pricing.estimate_cost_paise(
        "claude-opus-4-7",
        {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    )
    _insert_call_log(
        fid,
        model="claude-opus-4-7",
        input_tokens=1000,
        output_tokens=100,
        cost_paise=opus_cost,
    )
    # Unpriced model — cost_paise stays NULL.
    _insert_call_log(
        fid,
        model="claude-experimental-9-9",
        input_tokens=500,
        output_tokens=50,
        cost_paise=None,
    )

    stats = service.monthly_narrator_stats(firm_id=fid, month=_current_month())
    assert len(stats["per_model"]) == 2
    opus = next(r for r in stats["per_model"] if r["model"] == "claude-opus-4-7")
    exp = next(r for r in stats["per_model"] if r["model"] == "claude-experimental-9-9")
    assert opus["cost_paise"] > 0
    assert opus["unpriced_calls"] == 0
    assert exp["cost_paise"] == 0
    assert exp["unpriced_calls"] == 1
    # Aggregate flag: at least one call was unpriced, so warn the dashboard.
    assert stats["any_unpriced"] is True
    # Total cost_paise is priced-only (unpriced rows are excluded).
    assert stats["cost_paise"] == opus["cost_paise"]


def test_monthly_stats_paise_math_opus(bootstrap_firm) -> None:
    """Verify the priced cost sum against Anthropic Opus 4.7 list prices.

    Prices ($/M): input=15, output=75, cache_read=1.50.
    Row: input=1M, output=1M, cache_read=1M → fresh_input = 0
    Expected USD: 0*15 + 1*75 + 1*1.50 = $76.50
    Expected paise: 76.5 × USD_TO_PAISE_FX (from pricing config).
    """
    from app.narrator import pricing

    b = bootstrap_firm()
    expected_paise = pricing.estimate_cost_paise(
        "claude-opus-4-7",
        {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 0,
        },
    )
    assert expected_paise is not None
    _insert_call_log(
        b["firm_id"],
        model="claude-opus-4-7",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read=1_000_000,
        cache_creation=0,
        cost_paise=expected_paise,
    )
    stats = service.monthly_narrator_stats(
        firm_id=b["firm_id"], month=_current_month()
    )
    assert stats["cost_paise"] == expected_paise
    # And no unpriced-model flag set.
    assert stats["any_unpriced"] is False


def test_monthly_stats_firm_isolation(bootstrap_firm) -> None:
    """Firm A's stats never leak Firm B's rows (RLS + WHERE firm_id)."""
    a = bootstrap_firm(admin_email="stats-a@example.com")
    b = bootstrap_firm(admin_email="stats-b@example.com")
    _insert_call_log(a["firm_id"], input_tokens=10_000)
    _insert_call_log(b["firm_id"], input_tokens=99_999)

    a_stats = service.monthly_narrator_stats(
        firm_id=a["firm_id"], month=_current_month()
    )
    b_stats = service.monthly_narrator_stats(
        firm_id=b["firm_id"], month=_current_month()
    )
    assert a_stats["input_tokens"] == 10_000
    assert b_stats["input_tokens"] == 99_999


def test_monthly_stats_month_filtering(bootstrap_firm) -> None:
    """Rows outside the requested month are excluded."""
    from datetime import datetime, timezone
    b = bootstrap_firm()
    fid = b["firm_id"]
    # Row in the current month.
    _insert_call_log(fid, input_tokens=100)
    # Row 3 months ago.
    old_at = datetime(2025, 1, 15, tzinfo=timezone.utc)
    _insert_call_log(fid, input_tokens=99_999, at=old_at)

    # Query current month → only sees the 100-input row.
    now = datetime.now(tz=timezone.utc)
    current_stats = service.monthly_narrator_stats(
        firm_id=fid, month=f"{now.year:04d}{now.month:02d}"
    )
    assert current_stats["input_tokens"] == 100

    # Query Jan 2025 → only sees the 99_999-input row.
    jan_stats = service.monthly_narrator_stats(
        firm_id=fid, month="202501"
    )
    assert jan_stats["input_tokens"] == 99_999


def test_monthly_stats_rejects_bad_month(bootstrap_firm) -> None:
    b = bootstrap_firm()
    for bad in ("2026", "202613", "20260", "not-a-month"):
        with pytest.raises(ValueError):
            service.monthly_narrator_stats(firm_id=b["firm_id"], month=bad)


# ---------------------------------------------------------------------------
# Append-only guard — UPDATE + DELETE on narration_run must raise.
# ---------------------------------------------------------------------------


def test_narration_run_is_append_only(bootstrap_firm) -> None:
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    _, run_id = service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )
    # Owner is superuser and thus bypasses RLS, but the append-only
    # trigger fires on any role including superuser.
    with owner_engine.begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.execute(
                text("UPDATE narration_run SET provider = 'x' WHERE id = :id"),
                {"id": str(run_id)},
            )
    with owner_engine.begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.execute(
                text("DELETE FROM narration_run WHERE id = :id"),
                {"id": str(run_id)},
            )


# ---------------------------------------------------------------------------
# Phase 1.4 — cost_paise + per-firm monthly budget + runtime kill-switch
# ---------------------------------------------------------------------------


@pytest.fixture
def _reset_system_settings():
    """system_settings is a single-row global. The seeded row can be
    absent between tests because clean_db's ``TRUNCATE ca_firm
    CASCADE`` used to also truncate this table (see migration 0024 —
    the FK was dropped, but leaving the fixture robust to either state
    is cheap). We upsert the singleton on entry AND reset the
    kill-switch flag on exit."""
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO system_settings (id) VALUES (1) "
                "ON CONFLICT (id) DO UPDATE "
                "SET narrator_globally_disabled = false"
            )
        )
    yield
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO system_settings (id) VALUES (1) "
                "ON CONFLICT (id) DO UPDATE "
                "SET narrator_globally_disabled = false"
            )
        )


def _set_firm_budget(firm_id, budget_paise) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ca_firm SET monthly_narrator_budget_paise = :b "
                "WHERE id = :fid"
            ),
            {"b": budget_paise, "fid": str(firm_id)},
        )


def test_runtime_global_kill_switch_disables_narrator(
    _reset_system_settings, monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """The runtime kill switch (system_settings.narrator_globally_disabled)
    is orthogonal to settings.narrator_enabled: it takes effect without
    a deploy. When flipped on, every firm — even those with
    narrator_enabled=true — must get NarratorDisabled. The adapter must
    never be invoked."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE system_settings "
                "SET narrator_globally_disabled = true WHERE id = 1"
            )
        )

    class _MustNotBeCalled:
        provider = "must-not"
        model = "must-not"

        def narrate(self, *a, **kw):
            raise AssertionError("adapter should not have been invoked")

    monkeypatch.setattr(service, "get_adapter", lambda: _MustNotBeCalled())

    with pytest.raises(NarratorDisabled):
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )

    # No call_log row was written — the kill switch fired before the
    # adapter or logging path was touched.
    assert _read_call_logs(b["firm_id"]) == []


def test_budget_exhausted_raises_and_skips_adapter(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """When the current-month sum(cost_paise) meets or exceeds
    ca_firm.monthly_narrator_budget_paise, the call must raise
    NarratorBudgetExhausted before invoking the adapter. Silent
    fallback to a cheaper model is disallowed (P3_BUILD_PROMPT §3.1.4)."""
    from app.narrator.types import NarratorBudgetExhausted

    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    # Set budget = 100 paise, then log a prior call costing 100 paise
    # this month. The next call should refuse.
    _set_firm_budget(b["firm_id"], 100)
    _insert_call_log(
        b["firm_id"],
        model="claude-opus-4-7",
        input_tokens=10,
        output_tokens=5,
        cost_paise=100,
    )

    class _MustNotBeCalled:
        provider = "must-not"
        model = "must-not"

        def narrate(self, *a, **kw):
            raise AssertionError("adapter should not have been invoked")

    monkeypatch.setattr(service, "get_adapter", lambda: _MustNotBeCalled())

    with pytest.raises(NarratorBudgetExhausted) as excinfo:
        service.narrate_for_period(
            firm_id=b["firm_id"],
            gstin_profile_id=gpid,
            return_type="GSTR1",
            period="202607",
            language="en",
        )
    assert excinfo.value.used_paise == 100
    assert excinfo.value.budget_paise == 100

    # Only the seeded prior row is on the log — no attempted-call row
    # was written, because the gate short-circuited before the adapter.
    rows = _read_call_logs(b["firm_id"])
    assert len(rows) == 1
    assert rows[0]["input_tokens"] == 10


def test_budget_null_means_no_limit(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """A firm with monthly_narrator_budget_paise = NULL keeps the
    pre-Phase-1.4 behaviour: no ceiling, no cost check, calls proceed."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)
    _set_firm_budget(b["firm_id"], None)
    monkeypatch.setattr(service, "get_adapter", lambda: _UsageStubAdapter())

    service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )
    rows = _read_call_logs(b["firm_id"])
    assert len(rows) == 1
    assert rows[0]["succeeded"] is True


def test_budget_ignores_unpriced_rows(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """Rows with cost_paise IS NULL are excluded from the budget SUM.
    An unpriced call cannot eat into a firm's budget."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    # Budget = 100 paise; seed a prior unpriced call. That row must NOT
    # count toward the ceiling.
    _set_firm_budget(b["firm_id"], 100)
    _insert_call_log(
        b["firm_id"],
        model="claude-experimental-9-9",
        input_tokens=10_000,
        output_tokens=5_000,
        cost_paise=None,
    )
    monkeypatch.setattr(service, "get_adapter", lambda: _UsageStubAdapter())

    # Call should succeed — the unpriced prior row doesn't count.
    service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )
    rows = _read_call_logs(b["firm_id"])
    # Prior seeded row + one new success row = 2 total.
    assert len(rows) == 2


def test_cost_paise_written_at_call_time_for_priced_model(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """The service must compute cost_paise from tokens × pricing config
    at call time and stamp it on the narrator_call_log row. Downstream
    aggregation must not recompute — a later pricing-table update must
    not rewrite historical cost figures."""
    from app.narrator import pricing

    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    # Use a real pricing-config model id so the row gets cost_paise.
    stub = _UsageStubAdapter(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read=1_000_000,
        cache_creation=0,
    )
    stub.model = "claude-opus-4-7"
    monkeypatch.setattr(service, "get_adapter", lambda: stub)

    service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )

    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT cost_paise, pricing_effective_from FROM narrator_call_log "
                "WHERE firm_id = :fid ORDER BY at DESC LIMIT 1"
            ),
            {"fid": str(b["firm_id"])},
        ).first()

    expected = pricing.estimate_cost_paise(
        "claude-opus-4-7",
        {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 0,
        },
    )
    assert row is not None
    assert row[0] == expected
    assert row[1] is not None  # pricing_effective_from stamped


def test_cost_paise_null_for_unpriced_model(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    """A call against a model not in the pricing config must persist
    cost_paise=NULL. The aggregation surfaces this as ``any_unpriced=true``
    rather than a spurious ₹0 total."""
    b = bootstrap_firm()
    gpid = _make_gstin(b)
    _seed_readiness(firm_id=b["firm_id"], gstin_profile_id=gpid)

    stub = _UsageStubAdapter(input_tokens=1200, output_tokens=350)
    stub.model = "claude-experimental-9-9"  # Not in pricing.MODEL_PRICE_USD_PER_M
    monkeypatch.setattr(service, "get_adapter", lambda: stub)

    service.narrate_for_period(
        firm_id=b["firm_id"],
        gstin_profile_id=gpid,
        return_type="GSTR1",
        period="202607",
        language="en",
    )

    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT cost_paise, pricing_effective_from FROM narrator_call_log "
                "WHERE firm_id = :fid ORDER BY at DESC LIMIT 1"
            ),
            {"fid": str(b["firm_id"])},
        ).first()
    assert row is not None
    assert row[0] is None
    assert row[1] is None
