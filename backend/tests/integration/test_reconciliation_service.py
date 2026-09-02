"""End-to-end reconciliation service test.

Seeds a firm + gstin_profile, imports invoices + a 2B pull directly via
owner engine, then runs ``reconcile_period`` and asserts:

* reconciliation_run row is created with the correct pinning (rule pack
  version + gstn_pull_id + status='completed').
* match_result rows land, one per pair + one per residual, each with
  the right bucket + confidence.
* summary JSONB carries the expected counts + paise totals + top
  suppliers.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.engines.reconciliation.service import (
    NoTwoBPullError,
    reconcile_period,
)
from app.engines.validation.gstin import compute_check_digit


def _valid_gstin(base: str) -> str:
    return base + compute_check_digit(base)


CLIENT_GSTIN = _valid_gstin("29AAAAA0000A1Z")
SUP_A = _valid_gstin("29BBBBB1234C2Z")
SUP_B = _valid_gstin("27CCCCC5678D3Z")


@pytest.fixture
def firm_gstin(bootstrap_firm):
    admin = bootstrap_firm(admin_email="recon@example.com")
    firm_id = admin["firm_id"]
    gid = uuid.uuid4()
    with owner_engine.begin() as conn:
        cid = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:c, :f, 'Recon Client')"
            ),
            {"c": cid, "f": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:g, :f, :c, :gs, '29')"
            ),
            {"g": gid, "f": firm_id, "c": cid, "gs": CLIENT_GSTIN},
        )
    return firm_id, gid


def _insert_invoice(firm_id, gid, *, number, date_, cp, total) -> uuid.UUID:
    invoice_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO invoice (
                    id, firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise,
                    igst_paise, total_paise, content_hash
                ) VALUES (
                    :id, :f, :g, 'csv_import', 'purchase',
                    :num, :dt, :cp,
                    :tx, 0, 0, 0, :total, :h
                )
                """
            ),
            {
                "id": invoice_id,
                "f": firm_id,
                "g": gid,
                "num": number,
                "dt": date_,
                "cp": cp,
                "tx": total,
                "total": total,
                "h": f"h-{invoice_id}",
            },
        )
    return invoice_id


def _insert_gstn_pull_and_entries(
    firm_id, gid, *, period: str, entries: list[dict]
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    pull_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO gstn_pull (id, firm_id, gstin_profile_id,
                    return_type, period, raw_payload, source)
                VALUES (:id, :f, :g, 'GSTR2B', :p, CAST('{}' AS JSONB),
                    'json_import')
                """
            ),
            {"id": pull_id, "f": firm_id, "g": gid, "p": period},
        )
        entry_ids = []
        for e in entries:
            eid = uuid.uuid4()
            entry_ids.append(eid)
            conn.execute(
                text(
                    """
                    INSERT INTO b2b_entry (
                        id, firm_id, gstn_pull_id, supplier_gstin,
                        invoice_number, invoice_date,
                        taxable_value_paise, tax_paise_breakdown,
                        itc_available
                    ) VALUES (
                        :id, :f, :pid, :ctin,
                        :inum, :idt,
                        :tx, CAST(:tb AS JSONB),
                        TRUE
                    )
                    """
                ),
                {
                    "id": eid,
                    "f": firm_id,
                    "pid": pull_id,
                    "ctin": e["supplier"],
                    "inum": e["number"],
                    "idt": e["date"],
                    "tx": e["taxable"],
                    "tb": json.dumps(e.get("breakdown", {"cgst": 0, "sgst": 0, "igst": 0, "cess": 0})),
                },
            )
    return pull_id, entry_ids


# ---------------------------------------------------------------------------
# Happy path — one bucket of each type
# ---------------------------------------------------------------------------


def test_full_reconciliation_produces_four_buckets(firm_gstin) -> None:
    firm_id, gid = firm_gstin

    # register: matched, probable, supplier_default
    _insert_invoice(
        firm_id, gid,
        number="INV-M", date_=date(2026, 6, 15), cp=SUP_A, total=100_000,
    )
    _insert_invoice(
        firm_id, gid,
        number="INV-P", date_=date(2026, 6, 15), cp=SUP_A, total=50_000,
    )
    _insert_invoice(
        firm_id, gid,
        number="INV-SD", date_=date(2026, 6, 20), cp=SUP_B, total=30_000,
    )

    # 2B: matched to INV-M, probable-match to INV-P, missing_entry
    _insert_gstn_pull_and_entries(
        firm_id, gid,
        period="202606",
        entries=[
            # exact match to INV-M
            {"supplier": SUP_A, "number": "INV-M", "date": date(2026, 6, 15),
             "taxable": 100_000},
            # probable match to INV-P (slight date + amount diff)
            {"supplier": SUP_A, "number": "INV/P", "date": date(2026, 6, 17),
             "taxable": 50_100},
            # missing_entry — no register counterpart
            {"supplier": SUP_B, "number": "GHOST-1", "date": date(2026, 6, 15),
             "taxable": 8_000},
        ],
    )

    result = reconcile_period(firm_id, gid, "202606")
    assert result.rule_pack_version == "1.0.0"

    s = result.summary
    assert s["matched"]["count"] == 1
    assert s["matched"]["paise"] == 100_000
    assert s["probable"]["count"] == 1
    assert s["supplier_default"]["count"] == 1
    assert s["supplier_default"]["paise"] == 30_000
    assert s["missing_entry"]["count"] == 1
    assert "before credit/debit note adjustments" in s["disclaimer"]

    # Persisted rows: 1 matched + 1 probable + 1 supplier_default + 1 missing = 4
    with owner_engine.begin() as conn:
        by_bucket = dict(
            conn.execute(
                text(
                    "SELECT bucket::text, count(*) FROM match_result "
                    "WHERE firm_id = :f AND run_id = :r "
                    "GROUP BY bucket"
                ),
                {"f": str(firm_id), "r": str(result.run_id)},
            ).fetchall()
        )
    assert by_bucket == {
        "matched": 1,
        "probable": 1,
        "supplier_default": 1,
        "missing_entry": 1,
    }


def test_reconciliation_run_row_pins_provenance(firm_gstin) -> None:
    firm_id, gid = firm_gstin
    _insert_invoice(
        firm_id, gid,
        number="INV-1", date_=date(2026, 6, 15), cp=SUP_A, total=100_000,
    )
    pull_id, _ = _insert_gstn_pull_and_entries(
        firm_id, gid,
        period="202606",
        entries=[{"supplier": SUP_A, "number": "INV-1", "date": date(2026, 6, 15),
                  "taxable": 100_000}],
    )
    result = reconcile_period(firm_id, gid, "202606")
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT status, rule_pack_version, gstn_pull_id, "
                "finished_at IS NOT NULL AS done "
                "FROM reconciliation_run WHERE id = :id"
            ),
            {"id": str(result.run_id)},
        ).mappings().first()
    assert row["status"] == "completed"
    assert row["rule_pack_version"] == "1.0.0"
    assert row["gstn_pull_id"] == pull_id
    assert row["done"] is True


def test_reconciliation_raises_without_2b_pull(firm_gstin) -> None:
    firm_id, gid = firm_gstin
    _insert_invoice(
        firm_id, gid,
        number="INV-1", date_=date(2026, 6, 15), cp=SUP_A, total=100_000,
    )
    with pytest.raises(NoTwoBPullError):
        reconcile_period(firm_id, gid, "202606")


def test_supplier_default_persists_near_misses_in_context(firm_gstin) -> None:
    """A same-supplier 2B entry that fell outside the fuzzy amount
    tolerance must land in ``match_result.context.near_misses`` on the
    corresponding supplier_default row — so the dashboard can warn the
    CA before drafting a supplier chase.
    """
    firm_id, gid = firm_gstin

    _insert_invoice(
        firm_id, gid,
        number="INV-X", date_=date(2026, 6, 15), cp=SUP_A, total=50_000,
    )
    # Same supplier + same number, but taxable is way off (200%+): fuzzy
    # scoring disqualifies on amount tolerance, so it lands as near-miss.
    _insert_gstn_pull_and_entries(
        firm_id, gid,
        period="202606",
        entries=[
            {"supplier": SUP_A, "number": "INV-X", "date": date(2026, 6, 15),
             "taxable": 250_000},
        ],
    )

    result = reconcile_period(firm_id, gid, "202606")
    assert result.summary["supplier_default"]["with_near_misses"] == 1

    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT context FROM match_result "
                "WHERE run_id = :r AND bucket = 'supplier_default'"
            ),
            {"r": str(result.run_id)},
        ).mappings().first()
    ctx = row["context"]
    assert "near_misses" in ctx
    assert len(ctx["near_misses"]) == 1
    nm = ctx["near_misses"][0]
    assert nm["supplier_gstin"] == SUP_A
    assert nm["invoice_number"] == "INV-X"
    assert nm["similarity"] == 1.0
    # And the description carries the softer copy.
    desc = result.summary["supplier_default"]["description"].lower()
    assert "register-side error" in desc
    assert "review near_misses" in desc


def test_reconciliation_rls_isolates_across_firms(
    firm_gstin, bootstrap_firm
) -> None:
    firm_a, gid_a = firm_gstin

    # Setup firm B with its own gstin_profile + invoice + 2B pull.
    admin_b = bootstrap_firm(admin_email="firmb@example.com")
    firm_b = admin_b["firm_id"]
    gid_b = uuid.uuid4()
    with owner_engine.begin() as conn:
        cid = uuid.uuid4()
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) "
                 "VALUES (:c, :f, 'B')"),
            {"c": cid, "f": firm_b},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:g, :f, :c, :gs, '27')"
            ),
            {"g": gid_b, "f": firm_b, "c": cid,
             "gs": _valid_gstin("27DDDDD1111E1Z")},
        )
    _insert_invoice(
        firm_b, gid_b, number="B-1", date_=date(2026, 6, 15), cp=SUP_A,
        total=999_000,
    )
    _insert_gstn_pull_and_entries(
        firm_b, gid_b, period="202606",
        entries=[{"supplier": SUP_A, "number": "B-1",
                  "date": date(2026, 6, 15), "taxable": 999_000}],
    )

    # Now reconcile firm A — must not see firm B invoices or 2B entries.
    _insert_invoice(
        firm_a, gid_a, number="A-1", date_=date(2026, 6, 15), cp=SUP_A,
        total=100_000,
    )
    _insert_gstn_pull_and_entries(
        firm_a, gid_a, period="202606",
        entries=[{"supplier": SUP_A, "number": "A-1",
                  "date": date(2026, 6, 15), "taxable": 100_000}],
    )
    result = reconcile_period(firm_a, gid_a, "202606")

    # Only 1 pair, and totals reflect firm A only (100k, not 999k).
    assert result.summary["matched"]["count"] == 1
    assert result.summary["matched"]["paise"] == 100_000
