"""P2.1 STAGE A — adversarial reconciliation fixture tests.

Ten targeted cases against ``app/gsp/fixtures/gstr2b_29ADVRS0000A1ZA_202607.json``.
Each test asserts the SPECIFIC bucket (and where relevant, near-miss shape) the
matcher should produce — not merely that the pipeline completes.

Where the correct outcome is a domain judgment (A7 credit note, A10 tax-split,
A4 supplier typo), the test asserts the CONSERVATIVE current behaviour and the
question is added to the domain verification list in README.md. The word
"conservative" here means: same as P1 (default doesn't invent new business
rules) plus a TODO-VERIFY-WITH-CA marker in code.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import firm_scoped_session, owner_engine
from app.engines.reconciliation.service import reconcile_period
from app.ingestion.gstr2b_parser import parse_gstr2b_json
from app.ingestion.writer import bulk_insert_b2b_entries, insert_gstn_pull


FIXTURE_PATH = (
    Path(__file__).parent.parent.parent
    / "app" / "gsp" / "fixtures"
    / "gstr2b_29ADVRS0000A1ZA_202607.json"
)
CLIENT_GSTIN = "29ADVRS0000A1ZA"
PERIOD = "202607"


# Supplier GSTINs used by the fixture. Kept as constants so the tests read
# like a spec.
SUP_P = "29PPPPP0000A1ZP"          # A1, A2
SUP_Q = "29QQQQQ0000A1ZQ"          # A3 register + A3 same-supplier 2B
SUP_N = "29NNNNN0000A1ZN"          # A3 collision-supplier 2B
SUP_R_REG = "29RRRRR0000A1ZR"      # A4 register
SUP_R_TYPO = "29RRSRR0000A1ZR"     # A4 2B — one char different from SUP_R_REG
SUP_S = "29SSSSS0000A1ZS"          # A6 register only, no 2B
SUP_T = "29TTTTT0000A1ZT"          # A8
SUP_U = "29UUUUU0000A1ZU"          # A9
SUP_V = "29VVVVV0000A1ZV"          # A10
SUP_W = "29WWWWW0000A1ZW"          # A5 2B only
SUP_X = "29XXXXX0000A1ZX"          # A7 credit note (direct SQL insert)


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _seed_firm_and_client() -> dict:
    firm_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client_id = uuid.uuid4()
    gstin_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'AdvCo')"),
            {"id": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
                "totp_confirmed, is_active) "
                "VALUES (:id, :fid, 'adv@x.com', 'x', 'admin', TRUE, TRUE)"
            ),
            {"id": user_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, 'AdvClient')"
            ),
            {"cid": client_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, :g, '29')"
            ),
            {"gid": gstin_id, "fid": firm_id, "cid": client_id, "g": CLIENT_GSTIN},
        )
    return {"firm_id": firm_id, "user_id": user_id, "client_id": client_id,
            "gstin_profile_id": gstin_id}


def _insert_register_invoice(
    firm_id, gstin_profile_id, supplier, inum,
    invoice_date_iso, taxable, cgst, sgst, igst, total,
) -> uuid.UUID:
    """Insert a purchase-register invoice via the app engine and return its id."""
    inv_id = uuid.uuid4()
    # Content hash need only be unique per (gstin_profile_id, hash).
    h = hashlib.sha256(
        f"{gstin_profile_id}|{supplier}|{inum}|{invoice_date_iso}|{total}".encode()
    ).hexdigest()
    with firm_scoped_session(firm_id) as db:
        db.execute(
            text(
                """
                INSERT INTO invoice (
                    id, firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                    total_paise, content_hash
                ) VALUES (
                    :id, :fid, :gid, 'csv_import', 'purchase',
                    :inum, CAST(:idt AS DATE), :cp,
                    :tx, :cg, :sg, :ig,
                    :tot, :h
                )
                """
            ),
            {
                "id": inv_id, "fid": str(firm_id), "gid": str(gstin_profile_id),
                "inum": inum, "idt": invoice_date_iso, "cp": supplier,
                "tx": taxable, "cg": cgst, "sg": sgst, "ig": igst,
                "tot": total, "h": h,
            },
        )
    return inv_id


def _insert_credit_note_directly(firm_id, gstn_pull_id, supplier) -> uuid.UUID:
    """A7 helper. Parser doesn't process cdnr in P1/P2; this inserts a
    credit-note b2b_entry row directly so we can assert the DB-level
    ``note_type IS NULL`` filter in reconciliation._load_b2b."""
    cn_id = uuid.uuid4()
    with firm_scoped_session(firm_id) as db:
        db.execute(
            text(
                """
                INSERT INTO b2b_entry (
                    id, firm_id, gstn_pull_id, supplier_gstin,
                    invoice_number, invoice_date, taxable_value_paise,
                    tax_paise_breakdown, itc_available, note_type
                ) VALUES (
                    :id, :fid, :pid, :ctin,
                    'CN-A7', DATE '2026-07-05', 50000,
                    CAST('{}' AS JSONB), TRUE, CAST('credit_note' AS b2b_note_type)
                )
                """
            ),
            {"id": cn_id, "fid": str(firm_id), "pid": str(gstn_pull_id), "ctin": supplier},
        )
    return cn_id


# ---------------------------------------------------------------------------
# The scenario fixture — one setup per test, isolated by clean_db (autouse)
# ---------------------------------------------------------------------------


@pytest.fixture
def scenario():
    ff = _seed_firm_and_client()
    firm_id = ff["firm_id"]
    gpid = ff["gstin_profile_id"]

    # ---- Register-side seeds (8 invoices) ----
    reg_ids: dict[str, uuid.UUID] = {}
    reg_ids["A1"] = _insert_register_invoice(
        firm_id, gpid, SUP_P, "INV-A1", "2026-07-05",
        100000, 9000, 9000, 0, 118000,
    )
    reg_ids["A2"] = _insert_register_invoice(
        firm_id, gpid, SUP_P, "INV-A2", "2026-07-05",
        100000, 9000, 9000, 0, 118000,
    )
    reg_ids["A3"] = _insert_register_invoice(
        firm_id, gpid, SUP_Q, "INV-DUP", "2026-07-05",
        100000, 0, 0, 0, 100000,
    )
    reg_ids["A4"] = _insert_register_invoice(
        firm_id, gpid, SUP_R_REG, "INV-A4", "2026-07-05",
        100000, 0, 0, 0, 100000,
    )
    reg_ids["A6"] = _insert_register_invoice(
        firm_id, gpid, SUP_S, "INV-A6", "2026-07-05",
        100000, 0, 0, 0, 100000,
    )
    reg_ids["A8"] = _insert_register_invoice(
        firm_id, gpid, SUP_T, "INV-A8", "2026-07-05",
        100000, 0, 0, 0, 100000,
    )
    reg_ids["A9"] = _insert_register_invoice(
        firm_id, gpid, SUP_U, "INV-A9", "2026-07-05",
        100000, 0, 0, 0, 100000,
    )
    reg_ids["A10"] = _insert_register_invoice(
        firm_id, gpid, SUP_V, "INV-A10", "2026-07-05",
        100000, 9000, 9000, 0, 118000,
    )

    # ---- 2B-side load via shared writer (same path as GSP pull) ----
    payload = json.loads(FIXTURE_PATH.read_text())
    pull_id = insert_gstn_pull(
        firm_id=firm_id, gstin_profile_id=gpid, period=PERIOD,
        raw_payload=payload, source="gsp_api",
    )
    parse = parse_gstr2b_json(payload, gstn_pull_id=str(pull_id))
    bulk_insert_b2b_entries(firm_id=firm_id, gstn_pull_id=pull_id, entries=parse.entries)

    # ---- A7 credit note direct insert ----
    cn_id = _insert_credit_note_directly(firm_id, pull_id, SUP_X)

    # ---- Run reconciliation ----
    run = reconcile_period(firm_id=firm_id, gstin_profile_id=gpid, period=PERIOD)

    # ---- Index match_result rows by (invoice_id, b2b_entry_id) ----
    with owner_engine.begin() as conn:
        m_rows = conn.execute(
            text(
                "SELECT invoice_id, b2b_entry_id, bucket, confidence, context "
                "FROM match_result WHERE run_id = :r"
            ),
            {"r": str(run.run_id)},
        ).mappings().all()
        b2b_rows = conn.execute(
            text(
                "SELECT id, supplier_gstin, invoice_number, note_type "
                "FROM b2b_entry WHERE gstn_pull_id = :p ORDER BY supplier_gstin, invoice_number"
            ),
            {"p": str(pull_id)},
        ).mappings().all()

    return {
        "firm_id": firm_id, "gstin_profile_id": gpid, "pull_id": pull_id,
        "reg_ids": reg_ids, "cn_id": cn_id,
        "run_id": run.run_id, "summary": run.summary,
        "matches": [dict(r) for r in m_rows],
        "b2b_rows": [dict(r) for r in b2b_rows],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _match_for_invoice(matches, inv_id):
    hits = [m for m in matches if m["invoice_id"] == inv_id]
    assert len(hits) == 1, f"expected 1 match_result for invoice_id={inv_id}, got {len(hits)}"
    return hits[0]


def _matches_for_b2b(matches, b2b_id):
    return [m for m in matches if m["b2b_entry_id"] == b2b_id]


def _b2b_ids_by(b2b_rows, supplier, inum):
    return [r["id"] for r in b2b_rows if r["supplier_gstin"] == supplier and r["invoice_number"] == inum]


# ---------------------------------------------------------------------------
# A1 — 1-paise difference in taxable value → matched (within 100p tolerance)
# ---------------------------------------------------------------------------


def test_A1_one_paise_diff_in_taxable_still_matches(scenario) -> None:
    m = _match_for_invoice(scenario["matches"], scenario["reg_ids"]["A1"])
    assert m["bucket"] == "matched"
    assert float(m["confidence"]) == 1.0
    # The 2B side is the A1 row under supplier P
    (b2b_id,) = _b2b_ids_by(scenario["b2b_rows"], SUP_P, "INV-A1")
    assert m["b2b_entry_id"] == b2b_id


# ---------------------------------------------------------------------------
# A2 — 1-paise difference in tax only, taxable identical → still matched
# ---------------------------------------------------------------------------


def test_A2_one_paise_diff_in_tax_only_still_matches(scenario) -> None:
    m = _match_for_invoice(scenario["matches"], scenario["reg_ids"]["A2"])
    assert m["bucket"] == "matched"
    assert float(m["confidence"]) == 1.0


# ---------------------------------------------------------------------------
# A3 — same invoice number under two different supplier GSTINs
#      register-Q matches 2B-Q; 2B-N ends up as missing_entry
# ---------------------------------------------------------------------------


def test_A3_same_number_two_suppliers_pairs_same_supplier_and_orphans_the_other(scenario) -> None:
    # Register (INV-DUP under Q) → matched with 2B (INV-DUP under Q)
    m = _match_for_invoice(scenario["matches"], scenario["reg_ids"]["A3"])
    assert m["bucket"] == "matched"
    (b2b_q_id,) = _b2b_ids_by(scenario["b2b_rows"], SUP_Q, "INV-DUP")
    assert m["b2b_entry_id"] == b2b_q_id
    # 2B (INV-DUP under N) → missing_entry
    (b2b_n_id,) = _b2b_ids_by(scenario["b2b_rows"], SUP_N, "INV-DUP")
    n_matches = _matches_for_b2b(scenario["matches"], b2b_n_id)
    assert len(n_matches) == 1
    assert n_matches[0]["bucket"] == "missing_entry"
    assert n_matches[0]["invoice_id"] is None


# ---------------------------------------------------------------------------
# A4 — supplier GSTIN one character different → matcher CANNOT PAIR
#      Documented limitation. Register → supplier_default with ZERO near_misses.
# ---------------------------------------------------------------------------


def test_A4_supplier_gstin_one_char_typo_is_not_detected(scenario) -> None:
    # Register-side outcome: supplier_default with empty near_misses (limitation).
    m = _match_for_invoice(scenario["matches"], scenario["reg_ids"]["A4"])
    assert m["bucket"] == "supplier_default", (
        "matcher should NOT pair across differing supplier GSTINs "
        "(near-miss detection is same-supplier only — see V15 in domain list)"
    )
    context = m["context"] or {}
    assert context.get("near_misses", []) == [], (
        "no near-miss expected because the typo supplier is a different string "
        "and _find_near_misses hard-gates on b.supplier_gstin != r.supplier_gstin"
    )
    # 2B side: the typo-supplier row → missing_entry (no matching register row).
    (typo_id,) = _b2b_ids_by(scenario["b2b_rows"], SUP_R_TYPO, "INV-A4")
    typo_matches = _matches_for_b2b(scenario["matches"], typo_id)
    assert len(typo_matches) == 1
    assert typo_matches[0]["bucket"] == "missing_entry"


# ---------------------------------------------------------------------------
# A5 — invoice in 2B, no register → missing_entry
# ---------------------------------------------------------------------------


def test_A5_2b_only_invoice_is_missing_entry(scenario) -> None:
    (a5_id,) = _b2b_ids_by(scenario["b2b_rows"], SUP_W, "INV-A5")
    matches = _matches_for_b2b(scenario["matches"], a5_id)
    assert len(matches) == 1
    assert matches[0]["bucket"] == "missing_entry"
    assert matches[0]["invoice_id"] is None


# ---------------------------------------------------------------------------
# A6 — invoice in register, no 2B counterpart → supplier_default, no near-miss
# ---------------------------------------------------------------------------


def test_A6_register_only_invoice_is_supplier_default(scenario) -> None:
    m = _match_for_invoice(scenario["matches"], scenario["reg_ids"]["A6"])
    assert m["bucket"] == "supplier_default"
    context = m["context"] or {}
    # No 2B row exists for supplier S at all → no near-miss.
    assert context.get("near_misses", []) == []


# ---------------------------------------------------------------------------
# A7 — credit note in 2B is EXCLUDED FROM RECONCILIATION.
#
#      Domain question logged as V13 in README. Current conservative behaviour:
#      _load_b2b filters WHERE note_type IS NULL, so the credit note b2b_entry
#      is neither matched nor surfaced as a residual. The summary's frozen
#      disclaimer flags that ITC totals are "before credit/debit note
#      adjustments" — that label is what carries the caveat until the CA
#      answers V13.
# ---------------------------------------------------------------------------


def test_A7_credit_note_is_excluded_from_reconciliation(scenario) -> None:
    cn_id = scenario["cn_id"]
    # (a) The credit-note b2b_entry row exists in the DB…
    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT note_type FROM b2b_entry WHERE id = :id"),
            {"id": str(cn_id)},
        ).one()
    assert row[0] == "credit_note"
    # (b) …but it did NOT show up in match_result under any bucket.
    hits = _matches_for_b2b(scenario["matches"], cn_id)
    assert hits == [], (
        "credit note must be excluded by _load_b2b's note_type IS NULL filter "
        "until CDN netting semantics are answered (README V13)"
    )


def test_A7_frozen_cdn_disclaimer_still_appears_in_summary(scenario) -> None:
    # Frozen honest-label. Restyle OK, reword NOT OK.
    assert scenario["summary"]["disclaimer"] == "before credit/debit note adjustments"


# ---------------------------------------------------------------------------
# A8 — date supplied in %d/%m/%Y → parser accepts, invoice matches
# ---------------------------------------------------------------------------


def test_A8_slash_date_format_parses_and_matches(scenario) -> None:
    m = _match_for_invoice(scenario["matches"], scenario["reg_ids"]["A8"])
    assert m["bucket"] == "matched"
    # And confirm the b2b_entry date was stored as 2026-07-05, not raw string.
    with owner_engine.begin() as conn:
        b2b_date = conn.execute(
            text(
                "SELECT invoice_date FROM b2b_entry "
                "WHERE gstn_pull_id = :p AND supplier_gstin = :s AND invoice_number = 'INV-A8'"
            ),
            {"p": str(scenario["pull_id"]), "s": SUP_T},
        ).scalar_one()
    assert b2b_date == date(2026, 7, 5)


# ---------------------------------------------------------------------------
# A9 — same invoice twice in the same 2B payload
#      Pass 1 pairs one; the other is missing_entry
# ---------------------------------------------------------------------------


def test_A9_duplicate_2b_rows_pair_one_orphan_the_other(scenario) -> None:
    # Register row → matched
    m = _match_for_invoice(scenario["matches"], scenario["reg_ids"]["A9"])
    assert m["bucket"] == "matched"
    # Two b2b_entry rows exist for supplier U + INV-A9
    dup_ids = _b2b_ids_by(scenario["b2b_rows"], SUP_U, "INV-A9")
    assert len(dup_ids) == 2
    # Exactly one of them is the b2b_entry_id in the matched row.
    assert m["b2b_entry_id"] in dup_ids
    # The other appears as missing_entry.
    other = [i for i in dup_ids if i != m["b2b_entry_id"]][0]
    other_matches = _matches_for_b2b(scenario["matches"], other)
    assert len(other_matches) == 1
    assert other_matches[0]["bucket"] == "missing_entry"


# ---------------------------------------------------------------------------
# A10 — taxable equal, CGST+SGST (register) vs IGST (2B) → matched on totals
#
#       Domain question logged as V14. Current conservative behaviour:
#       matcher works on totals only; tax breakdown is not consulted. This
#       test locks THAT behaviour so a future change (e.g. demote to
#       probable, or attach a warning to context) breaks the test loudly.
# ---------------------------------------------------------------------------


def test_A10_tax_split_mismatch_still_matches_at_equal_totals(scenario) -> None:
    m = _match_for_invoice(scenario["matches"], scenario["reg_ids"]["A10"])
    assert m["bucket"] == "matched", (
        "conservative current behaviour: matcher works on total_paise only "
        "(see V14 in domain list — CA to confirm whether tax-split mismatch "
        "should demote to probable or attach a warning to match_result.context)"
    )
    (b2b_id,) = _b2b_ids_by(scenario["b2b_rows"], SUP_V, "INV-A10")
    assert m["b2b_entry_id"] == b2b_id
    # And confirm the tax breakdown really did differ: register CGST+SGST, 2B IGST.
    with owner_engine.begin() as conn:
        tb = conn.execute(
            text("SELECT tax_paise_breakdown FROM b2b_entry WHERE id = :id"),
            {"id": str(b2b_id)},
        ).scalar_one()
    assert int(tb["igst"]) == 18000
    assert int(tb["cgst"]) == 0 and int(tb["sgst"]) == 0


# ---------------------------------------------------------------------------
# Overall summary sanity — locks the exact bucket counts + itc-split totals
# so a matcher change breaks in ONE aggregate assertion instead of drifting
# silently across the case-specific tests.
# ---------------------------------------------------------------------------


def test_summary_bucket_totals_match_predictions(scenario) -> None:
    s = scenario["summary"]
    # Matched: A1, A2, A3-Q, A8, A9, A10 → 6
    assert s["matched"]["count"] == 6
    # Probable: none
    assert s["probable"]["count"] == 0
    # supplier_default: A4-reg, A6-reg → 2
    assert s["supplier_default"]["count"] == 2
    # missing_entry: A3-N, A4-typo-2B, A5, A9-dup-2 → 4
    assert s["missing_entry"]["count"] == 4
    # ITC split — all matched entries in this fixture are itc_available=True,
    # so paise_claimable == paise, paise_not_available == 0.
    assert s["matched"]["paise_claimable"] == s["matched"]["paise"]
    assert s["matched"]["paise_not_available"] == 0
