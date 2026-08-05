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
    NumberHallucination,
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
