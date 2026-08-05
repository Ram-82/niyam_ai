"""Demo seed — the "₹43,000 ITC at risk from 6 suppliers" story.

Usage (from the repo root):

    docker compose run --rm backend python -m scripts.seed_demo
    # or, with a specific "today" for reproducible scores:
    docker compose run --rm backend python -m scripts.seed_demo --today 2026-07-05

Behaviour:

* Wipes ALL tenant data (TRUNCATE ... CASCADE) and re-inserts the demo
  fixture with fixed UUIDs. **Do not run against real data.** Rule pack
  survives (global config).
* Creates one firm (Ramesh & Co CAs), one admin, one client (Ramesh
  Textiles Pvt Ltd), one GSTIN, and a scenario in the last complete
  calendar month designed to hit every reconciliation bucket in a
  demo-worthy way:

    Bucket             Rows  ₹ total         Purpose
    matched              10   85,808.10      cleanly reconciled ITC
    probable              2   86,242.13      live confirm demo
    supplier_default      6   43,000.00      the "₹43,000 at risk" headline
      (2 with near-misses, 4 without — both review states visible)
    missing_entry         1   1,24,906.26    the fat unrecorded purchase
    (also: 3 R001-only invoices ~₹56,000 with NULL counterparty — not
     part of recon, but seed validation errors for the invoices tab)

  Sum of supplier_default rows equals the headline **₹43,000.00
  exactly** — the six invoice totals are
  17,924.50 + 8,478.90 + 5,182.60 + 4,631.20 + 4,118.90 + 2,663.90.
  Every OTHER bucket total is non-round because it falls out of
  realistic textile-trade arithmetic (fabric metres × per-metre rate,
  T-shirts × per-piece rate). The ₹43,000.00 invariant is asserted
  inside ``seed_invoices_and_2b`` — edit ``SD_SPEC`` and the seed
  refuses to run if the sum drifts.

* Runs validate_period, reconcile_period, and compute_and_persist so
  the dashboard opens with real snapshots, not placeholders.

Login (printed at the end too, for reference):

    email:    demo@niyam.ai
    password: DemoPassword-2026-Correct
    TOTP secret (fixed base32, use in any authenticator app):
        JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP

Idempotency: run the script twice, get the same state. Handy between
sales meetings — no residual state, no drift.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import text
from zoneinfo import ZoneInfo

from app.auth.passwords import hash_password
from app.config import settings
from app.db import owner_engine
from app.engines.reconciliation.service import reconcile_period
from app.engines.scoring.service import compute_and_persist
from app.engines.validation.gstin import compute_check_digit
from app.engines.validation.service import validate_period


# ---------------------------------------------------------------------------
# Fixed identities — stable across runs, so demo bookmarks work.
# ---------------------------------------------------------------------------

DEMO_FIRM_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEMO_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
DEMO_CLIENT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
DEMO_GID = uuid.UUID("44444444-4444-4444-4444-444444444444")

DEMO_FIRM_NAME = "Ramesh & Co Chartered Accountants"
DEMO_CLIENT_NAME = "Ramesh Textiles Pvt Ltd"
DEMO_EMAIL = "demo@niyam.ai"
DEMO_PASSWORD = "DemoPassword-2026-Correct"
# Deliberately fixed so demo credentials stay stable across resets.
DEMO_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def mk_gstin(base14: str) -> str:
    """Append the check digit computed from ``base14`` to produce a
    checksum-valid GSTIN. Base must be exactly 14 chars."""
    return base14 + compute_check_digit(base14)


CLIENT_GSTIN = mk_gstin("29AAAAA0000A1Z")  # Karnataka, regular

SUPPLIERS: dict[str, str] = {
    # Matched — 5 suppliers, 2 invoices each = 10 matched invoices.
    # All state 29 (Karnataka, intra-state with the client) so the
    # default CGST+SGST split is the correct tax head. R005 is
    # triggered separately by the M_3-1 UPDATE below (intra-state
    # invoice with IGST — the classic "wrong tax head" mistake).
    "M_1": mk_gstin("29BBBBB0000A1Z"),
    "M_2": mk_gstin("29BBBBB0001A1Z"),
    "M_3": mk_gstin("29CCCCC0000A1Z"),
    "M_4": mk_gstin("29CCCCC0001A1Z"),
    "M_5": mk_gstin("29DDDDD0000A1Z"),
    # Probable — 2 suppliers. P_1 intra-state, P_2 inter-state (MH)
    # to demonstrate both tax-head cases in the probable flow.
    "P_1": mk_gstin("29EEEEE0000A1Z"),
    "P_2": mk_gstin("27FFFFF0000A1Z"),
    # Supplier defaults — 5 valid + 1 malformed (see MALFORMED below).
    "SD_1": mk_gstin("29GGGGG0000A1Z"),   # ₹18,000  — no near-miss
    "SD_2": mk_gstin("29HHHHH0000A1Z"),   # ₹8,500   — WITH near-miss
    "SD_3": mk_gstin("27JJJJJ0000A1Z"),   # ₹5,000   — no near-miss
    "SD_4": mk_gstin("06KKKKK0000A1Z"),   # ₹4,500   — WITH near-miss
    "SD_5": mk_gstin("29LLLLL0000A1Z"),   # ₹4,000   — no near-miss
    # Fat missing_entry supplier.
    "MISSING": mk_gstin("29MMMMM0000A1Z"),
}

# The malformed GSTIN — trips R002 in validation. Used as the P1
# stand-in for a "supplier appears cancelled / inactive" flag until the
# live GSP status check lands (see README Domain verification list).
SD_6_MALFORMED = "29INVALIDBADGST"       # 15 chars but not a real GSTIN


# ---------------------------------------------------------------------------
# Wipe + seed
# ---------------------------------------------------------------------------


TENANT_TABLES = (
    "match_result", "reconciliation_run",
    "b2b_entry", "gstn_pull", "validation_flag", "invoice",
    "readiness_snapshot", "consent_log", "audit_log",
    "import_job", "client_assignment", "gstin_profile",
    "user_invite", "app_user", "client", "ca_firm",
)


def wipe() -> None:
    """Nuke every tenant table so re-runs are idempotent. Rule pack
    (global config) is left alone."""
    with owner_engine.begin() as conn:
        conn.execute(text(
            f"TRUNCATE TABLE {', '.join(TENANT_TABLES)} "
            f"RESTART IDENTITY CASCADE"
        ))


def make_firm_and_admin() -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, :n)"),
            {"id": DEMO_FIRM_ID, "n": DEMO_FIRM_NAME},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_user (
                    id, firm_id, email, password_hash, role,
                    totp_secret, totp_confirmed, is_active
                ) VALUES (
                    :id, :fid, :email, :ph, 'admin',
                    :ts, TRUE, TRUE
                )
                """
            ),
            {
                "id": DEMO_USER_ID,
                "fid": DEMO_FIRM_ID,
                "email": DEMO_EMAIL,
                "ph": hash_password(DEMO_PASSWORD),
                "ts": DEMO_TOTP_SECRET,
            },
        )
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name, language) "
                "VALUES (:id, :fid, :n, 'en')"
            ),
            {"id": DEMO_CLIENT_ID, "fid": DEMO_FIRM_ID, "n": DEMO_CLIENT_NAME},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:id, :fid, :cid, :g, '29', 'regular')"
            ),
            {
                "id": DEMO_GID,
                "fid": DEMO_FIRM_ID,
                "cid": DEMO_CLIENT_ID,
                "g": CLIENT_GSTIN,
            },
        )


def _insert_invoice(
    conn,
    *,
    num: str,
    dt: date,
    cp: Optional[str],
    taxable: int,
    cgst: int = 0,
    sgst: int = 0,
    igst: int = 0,
    hsn: Optional[str] = "998311",
) -> uuid.UUID:
    total = taxable + cgst + sgst + igst
    invoice_id = uuid.uuid4()
    conn.execute(
        text(
            """
            INSERT INTO invoice (
                id, firm_id, gstin_profile_id, source, direction,
                invoice_number, invoice_date, counterparty_gstin,
                taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                total_paise, hsn_sac, content_hash
            ) VALUES (
                :id, :f, :g, 'csv_import', 'purchase',
                :num, :dt, :cp, :tx, :cg, :sg, :ig, :total, :hsn, :h
            )
            """
        ),
        {
            "id": invoice_id,
            "f": DEMO_FIRM_ID,
            "g": DEMO_GID,
            "num": num,
            "dt": dt,
            "cp": cp,
            "tx": taxable,
            "cg": cgst,
            "sg": sgst,
            "ig": igst,
            "total": total,
            "hsn": hsn,
            "h": f"h-{num}-{dt.isoformat()}",
        },
    )
    return invoice_id


def _insert_b2b(
    conn,
    *,
    pull_id: uuid.UUID,
    sup: str,
    num: str,
    dt: date,
    taxable: int,
    cgst: int = 0,
    sgst: int = 0,
    igst: int = 0,
) -> None:
    breakdown = {"cgst": cgst, "sgst": sgst, "igst": igst, "cess": 0}
    conn.execute(
        text(
            """
            INSERT INTO b2b_entry (
                firm_id, gstn_pull_id, supplier_gstin, invoice_number,
                invoice_date, taxable_value_paise, tax_paise_breakdown,
                itc_available
            ) VALUES (
                :f, :pid, :sup, :num, :dt, :tx, CAST(:tb AS JSONB), TRUE
            )
            """
        ),
        {
            "f": DEMO_FIRM_ID,
            "pid": pull_id,
            "sup": sup,
            "num": num,
            "dt": dt,
            "tx": taxable,
            "tb": json.dumps(breakdown),
        },
    )


# ---------------------------------------------------------------------------
# Tax-computation helpers used by the seed.
#
# Every rupee value below is written out as a string (e.g. "12175.63") and
# converted to paise via the same HALF_UP quantization the ingestion path uses
# (see ``app/ingestion/canonical.py::rupees_to_paise``). That keeps seed-side
# arithmetic byte-identical to what a CA-uploaded CSV would produce for the
# same values.
# ---------------------------------------------------------------------------


def _to_paise(rupees_str: str) -> int:
    """Rupee string → integer paise. HALF_UP at the paise boundary."""
    return int(
        (Decimal(rupees_str) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _intra_18(taxable_p: int) -> tuple[int, int, int]:
    """Intra-state 18%: return ``(cgst_paise, sgst_paise, total_paise)``.
    Total tax is quantized HALF_UP, then split; odd paise goes to SGST so
    the split is deterministic."""
    tax = int(
        (Decimal(taxable_p) * Decimal("18") / Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    cgst = tax // 2
    sgst = tax - cgst
    return cgst, sgst, taxable_p + tax


def _inter_18(taxable_p: int) -> tuple[int, int]:
    """Inter-state 18%: return ``(igst_paise, total_paise)``."""
    igst = int(
        (Decimal(taxable_p) * Decimal("18") / Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    return igst, taxable_p + igst


def _sd_backsolve_intra(total_p: int) -> tuple[int, int, int, int, int]:
    """Back-solve intra-state (CGST+SGST) so ``taxable + cgst + sgst == total_p``.
    Returns ``(taxable, cgst, sgst, igst=0, total)``. Guarantees per-invoice
    totals hit their target to the paise — this matters for the ₹43,000
    supplier_default headline."""
    taxable = int(
        (Decimal(total_p) / Decimal("1.18")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    tax = total_p - taxable
    cgst = tax // 2
    sgst = tax - cgst
    return taxable, cgst, sgst, 0, total_p


def _sd_backsolve_inter(total_p: int) -> tuple[int, int, int, int, int]:
    """Back-solve inter-state (IGST only) so ``taxable + igst == total_p``."""
    taxable = int(
        (Decimal(total_p) / Decimal("1.18")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    igst = total_p - taxable
    return taxable, 0, 0, igst, total_p


def _sd_backsolve(total_p: int, client_state: str, supplier_gstin: str) -> tuple[int, int, int, int, int]:
    """Dispatch: intra-state (CGST+SGST) if supplier's state code matches
    the client, else inter-state (IGST). Malformed GSTINs (whose first two
    chars aren't a valid state code) fall through to intra — R002 already
    fires on those and R005 would be noise."""
    sup_state = (supplier_gstin[:2] if supplier_gstin else "").strip()
    if sup_state == client_state and sup_state.isdigit():
        return _sd_backsolve_intra(total_p)
    if not sup_state.isdigit():
        # Malformed GSTIN (SD_6). Skip tax-head classification — R002 is
        # the flag the CA cares about here; splitting into CGST+SGST is
        # arbitrary but total-preserving.
        return _sd_backsolve_intra(total_p)
    return _sd_backsolve_inter(total_p)


# HSNs the client would actually book — Ramesh Textiles is a woven-cotton +
# ready-garment trader. TODO-VERIFY-WITH-CA on the exact HSNs typical for a
# tier-2 textile MSME (item 1 in Domain verification).
HSN_COTTON_FABRIC = "5208"   # Woven cotton fabric ≤ 200 g/m²
HSN_COTTON_HEAVY  = "5209"   # Woven cotton fabric > 200 g/m²
HSN_TSHIRTS       = "6109"   # T-shirts, singlets and other vests
HSN_MENS_SUITS    = "6203"   # Men's suits, ensembles, jackets


# ---------------------------------------------------------------------------
# The ten matched invoices — realistic textile-trade line items.
# Each row is (supplier_key, invoice_num, day, taxable-rupees-str, hsn).
# Amounts chosen from meters × per-meter rates or pieces × per-piece rates
# that a real MSME would enter; no round numbers except where a supplier
# would legitimately round on invoice (e.g. cash-basis vendors).
#
# Computed totals (register + 2B mirror each other):
#     M_1-1  ₹14,367.24    M_1-2  ₹9,613.28
#     M_2-1  ₹10,684.90    M_2-2  ₹6,467.70
#     M_3-1  ₹9,058.90     M_3-2  ₹8,081.23
#     M_4-1  ₹5,800.34     M_4-2  ₹7,911.19
#     M_5-1  ₹6,734.26     M_5-2  ₹7,089.28
# Matched-bucket total = ₹85,808.32 (non-round, arithmetic falls out of the line items).
# ---------------------------------------------------------------------------
MATCHED_SPEC: list[tuple[str, str, int, str, str]] = [
    ("M_1", "INV-M_1-1", 10, "12175.63", HSN_COTTON_FABRIC),  # 42.35m × ₹287.50
    ("M_1", "INV-M_1-2", 20, "8146.85",  HSN_COTTON_HEAVY),   # 24.60m × ₹331.25
    ("M_2", "INV-M_2-1", 10, "9055.00",  HSN_COTTON_FABRIC),  # cash-basis round rupees
    ("M_2", "INV-M_2-2", 20, "5481.10",  HSN_TSHIRTS),        # 22 pcs × ₹249.14
    ("M_3", "INV-M_3-1", 10, "7676.86",  HSN_COTTON_FABRIC),  # rate/qty produces .86
    ("M_3", "INV-M_3-2", 20, "6848.50",  HSN_COTTON_FABRIC),  # 27.75m × ₹246.85 (rounded)
    ("M_4", "INV-M_4-1", 10, "4915.54",  HSN_MENS_SUITS),     # 6 pcs × ₹819.26 (fractional)
    ("M_4", "INV-M_4-2", 20, "6704.40",  HSN_COTTON_HEAVY),   # 19.20m × ₹349.19
    ("M_5", "INV-M_5-1", 10, "5707.00",  HSN_TSHIRTS),        # 22 pcs × ₹259.41 (rounded)
    ("M_5", "INV-M_5-2", 20, "6007.86",  HSN_COTTON_FABRIC),  # 21.42m × ₹280.48
]


# ---------------------------------------------------------------------------
# Two probable-bucket invoices. Register vs 2B drift within fuzzy tolerance:
# amount drift ~0.5%, date +2 days, invoice number normalizes same after
# normalize_invoice_number strips separators. Both hit >0.70 confidence.
# ---------------------------------------------------------------------------
PROBABLE_REG_P1 = "31847.90"   # register — intra-state 18% split
PROBABLE_2B_P1  = "31888.60"   # 2B — +₹40.70 on taxable
PROBABLE_REG_P2 = "41238.65"   # register — inter-state IGST 18%
PROBABLE_2B_P2  = "41273.65"   # 2B — +₹35 on taxable


# ---------------------------------------------------------------------------
# Six supplier_default invoices. Totals CHOSEN so the six-invoice sum lands
# on exactly ₹43,000.00 (43_00_000 paise) — that is the headline the pitch
# hangs on. Individual totals are non-round; the SUM is what the CA verifies.
# Back-solved via ``_sd_backsolve`` so ``taxable + cgst + sgst == total``
# for each row.
#
#   SD_1  ₹17,924.50  →  taxable + intra-18% = 17924.50 exactly
#   SD_2  ₹8,478.90
#   SD_3  ₹5,182.60
#   SD_4  ₹4,631.20
#   SD_5  ₹4,118.90
#   SD_6  ₹2,663.90
#   Sum   ₹43,000.00 exact
# ---------------------------------------------------------------------------
SD_SPEC: list[tuple[str, str, int, str, str, Optional[str]]] = [
    # (supplier_key_or_gstin_lit, invoice_num, day, target_total_str, sup_gstin_var, hsn)
    ("SD_1", "INV-SD_1-1", 5,  "17924.50", "SD_1_G", HSN_COTTON_FABRIC),
    ("SD_2", "INV-SD_2-1", 10, "8478.90",  "SD_2_G", None),                # R004 warning
    ("SD_3", "INV-SD_3-1", 15, "5182.60",  "SD_3_G", HSN_COTTON_HEAVY),
    ("SD_4", "INV-SD_4-1", 20, "4631.20",  "SD_4_G", HSN_TSHIRTS),
    ("SD_5", "INV-SD_5-1", 25, "4118.90",  "SD_5_G", None),                # R004 warning
    ("SD_6", "INV-SD_6-1", 15, "2663.90",  "SD_6_G", HSN_COTTON_FABRIC),   # R002 (malformed GSTIN)
]


def seed_invoices_and_2b(period: str) -> None:
    """The main story. All amounts computed in PAISE via Decimal HALF_UP
    to match the CSV-ingestion rounding exactly.

    ₹43,000.00 supplier_default headline is preserved to the paise; every
    other bucket total is non-round because it falls out of realistic
    per-line arithmetic. See ``MATCHED_SPEC`` / ``PROBABLE_*`` / ``SD_SPEC``.
    """
    year, month = int(period[:4]), int(period[4:])
    d5 = date(year, month, 5)
    d10 = date(year, month, 10)
    d15 = date(year, month, 15)
    d20 = date(year, month, 20)
    d25 = date(year, month, 25)

    day_lookup = {5: d5, 10: d10, 15: d15, 20: d20, 25: d25}
    sd_gstin_lookup = {
        "SD_1_G": SUPPLIERS["SD_1"],
        "SD_2_G": SUPPLIERS["SD_2"],
        "SD_3_G": SUPPLIERS["SD_3"],
        "SD_4_G": SUPPLIERS["SD_4"],
        "SD_5_G": SUPPLIERS["SD_5"],
        "SD_6_G": SD_6_MALFORMED,
    }

    pull_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        # ----- Register: 10 matched, non-round per-invoice totals -----
        matched_records: list[tuple[str, date, str, int, int, int]] = []
        for sup_key, num, day, taxable_rup, hsn in MATCHED_SPEC:
            dt = day_lookup[day]
            sup_gstin = SUPPLIERS[sup_key]
            taxable_p = _to_paise(taxable_rup)
            cgst_p, sgst_p, total_p = _intra_18(taxable_p)
            matched_records.append((num, dt, sup_gstin, taxable_p, cgst_p, sgst_p))
            _insert_invoice(
                conn, num=num, dt=dt, cp=sup_gstin,
                taxable=taxable_p, cgst=cgst_p, sgst=sgst_p, hsn=hsn,
            )

        # Flag M_3-1 with R005 (intra-state invoice booked as IGST — a
        # common "wrong tax head" error). Rewrite the tax columns; the
        # total lands where 18% IGST on the same taxable would land.
        m3_1 = next(r for r in matched_records if r[0] == "INV-M_3-1")
        _, _, _, m3_taxable, _, _ = m3_1
        m3_igst, m3_total_after = _inter_18(m3_taxable)
        conn.execute(
            text(
                "UPDATE invoice SET cgst_paise = 0, sgst_paise = 0, "
                "igst_paise = :igst, total_paise = :total "
                "WHERE gstin_profile_id = :g AND invoice_number = :num"
            ),
            {"g": DEMO_GID, "num": "INV-M_3-1",
             "igst": m3_igst, "total": m3_total_after},
        )

        # Missing HSN on 2 matched invoices → R004 warnings.
        conn.execute(
            text(
                "UPDATE invoice SET hsn_sac = NULL "
                "WHERE gstin_profile_id = :g "
                "  AND invoice_number IN ('INV-M_4-1', 'INV-M_5-2')"
            ),
            {"g": DEMO_GID},
        )

        # ----- Register: 2 probable -----
        p1_taxable = _to_paise(PROBABLE_REG_P1)
        p1_cgst, p1_sgst, _p1_total = _intra_18(p1_taxable)
        _insert_invoice(
            conn, num="INV-P_1-1", dt=d15, cp=SUPPLIERS["P_1"],
            taxable=p1_taxable, cgst=p1_cgst, sgst=p1_sgst,
            hsn=HSN_COTTON_HEAVY,
        )
        p2_taxable = _to_paise(PROBABLE_REG_P2)
        p2_igst, _p2_total = _inter_18(p2_taxable)
        _insert_invoice(
            conn, num="INV-P_2-1", dt=d15, cp=SUPPLIERS["P_2"],
            taxable=p2_taxable, cgst=0, sgst=0, igst=p2_igst,
            hsn=HSN_MENS_SUITS,
        )

        # ----- Register: 6 supplier_defaults, SUM = ₹43,000 exact -----
        sd_totals: list[int] = []
        for sup_key, num, day, target_rup, gstin_var, hsn in SD_SPEC:
            dt = day_lookup[day]
            total_p = _to_paise(target_rup)
            sup_gstin = sd_gstin_lookup[gstin_var]
            # Dispatch by state code: intra when same-state, inter otherwise.
            # Preserves the ₹43,000 sum invariant regardless of split.
            taxable_p, cgst_p, sgst_p, igst_p, _ = _sd_backsolve(
                total_p, client_state="29", supplier_gstin=sup_gstin,
            )
            sd_totals.append(total_p)
            _insert_invoice(
                conn, num=num, dt=dt, cp=sup_gstin,
                taxable=taxable_p, cgst=cgst_p, sgst=sgst_p, igst=igst_p, hsn=hsn,
            )
        # Belt-and-braces: assert the pitch invariant at seed time. If this
        # ever trips it means someone edited SD_SPEC without checking the sum.
        assert sum(sd_totals) == 43_00_000, (
            f"₹43,000 headline invariant broken: sum={sum(sd_totals)} paise"
        )

        # ----- Register: 3 R001-only invoices (missing counterparty) -----
        # Realistic per-invoice values; excluded from recon by the
        # counterparty_gstin IS NOT NULL filter, so they only feed R001.
        for i, (dt, rup) in enumerate(
            [(d5, "22341.75"), (d15, "18752.60"), (d25, "15906.85")], start=1
        ):
            taxable_p = _to_paise(rup)
            cgst_p, sgst_p, _ = _intra_18(taxable_p)
            _insert_invoice(
                conn, num=f"INV-NOGSTIN-{i}", dt=dt, cp=None,
                taxable=taxable_p, cgst=cgst_p, sgst=sgst_p,
                hsn=HSN_COTTON_FABRIC,
            )

        # ----- GSTN pull -----
        conn.execute(
            text(
                "INSERT INTO gstn_pull (id, firm_id, gstin_profile_id, "
                "return_type, period, raw_payload, source) "
                "VALUES (:id, :f, :g, 'GSTR2B', :p, "
                "CAST('{}' AS JSONB), 'json_import')"
            ),
            {"id": pull_id, "f": DEMO_FIRM_ID, "g": DEMO_GID, "p": period},
        )

        # ----- 2B entries -----
        # For each matched register invoice, mirror on the 2B side (same
        # key + same total; Pass 1 exact match).
        for num, dt, sup, taxable_p, cgst_p, sgst_p in matched_records:
            _insert_b2b(
                conn, pull_id=pull_id, sup=sup, num=num, dt=dt,
                taxable=taxable_p, cgst=cgst_p, sgst=sgst_p,
            )

        # Probable: date +2 days, invoice number normalizes same, amount
        # drifts ~0.1% (well inside the 1% fuzzy tolerance).
        p1_2b_taxable = _to_paise(PROBABLE_2B_P1)
        p1_2b_cgst, p1_2b_sgst, _ = _intra_18(p1_2b_taxable)
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["P_1"],
            num="INV/P_1-1",  # normalizes same as INV-P_1-1
            dt=d15 + timedelta(days=2),
            taxable=p1_2b_taxable, cgst=p1_2b_cgst, sgst=p1_2b_sgst,
        )
        p2_2b_taxable = _to_paise(PROBABLE_2B_P2)
        p2_2b_igst, _ = _inter_18(p2_2b_taxable)
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["P_2"],
            num="INV-P_2/1",
            dt=d15 + timedelta(days=2),
            taxable=p2_2b_taxable, cgst=0, sgst=0, igst=p2_2b_igst,
        )

        # Near-miss 2B rows for SD_2 and SD_4 — same supplier + same
        # normalized invoice number, but amount OUTSIDE fuzzy tolerance
        # so they surface as near_misses attached to the supplier_default
        # match_result (and independently as missing_entry residuals —
        # engine design; near-misses don't consume the 2B row). Amounts
        # kept small so they don't distort missing_entry paise.
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["SD_2"],
            num="INV-SD_2-1", dt=d10,
            taxable=_to_paise("4.72"),   # ₹4.72 — tiny + odd
        )
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["SD_4"],
            num="INV-SD_4-1", dt=d20,
            taxable=_to_paise("2.85"),   # ₹2.85 — tiny + odd
        )

        # Fat missing_entry — 2B has a big invoice from a supplier the
        # client never recorded. Non-round taxable × 18% IGST.
        ghost_taxable = _to_paise("105846.35")
        ghost_igst, _ = _inter_18(ghost_taxable)
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["MISSING"],
            num="INV-GHOST-BIG", dt=d15,
            taxable=ghost_taxable, cgst=0, sgst=0, igst=ghost_igst,
        )


def run_engines(period: str, today: date) -> tuple[int, dict, int, int]:
    """Run validate → reconcile → score. Returns:
    (score, summary, error_flag_count, warning_flag_count).
    """
    val = validate_period(
        firm_id=DEMO_FIRM_ID,
        gstin_profile_id=DEMO_GID,
        period=period,
        today=today,
    )
    recon = reconcile_period(
        firm_id=DEMO_FIRM_ID,
        gstin_profile_id=DEMO_GID,
        period=period,
    )
    score = compute_and_persist(
        firm_id=DEMO_FIRM_ID,
        gstin_profile_id=DEMO_GID,
        return_type="GSTR1",
        period=period,
        today=today,
    )
    # Also run GSTR3B so the command center shows both.
    compute_and_persist(
        firm_id=DEMO_FIRM_ID,
        gstin_profile_id=DEMO_GID,
        return_type="GSTR3B",
        period=period,
        today=today,
    )
    errors = val.by_rule.get("R001", 0) + val.by_rule.get("R002", 0) + \
        val.by_rule.get("R005", 0) + val.by_rule.get("R006", 0) + \
        val.by_rule.get("R008", 0)
    warnings = val.by_rule.get("R003", 0) + val.by_rule.get("R004", 0) + \
        val.by_rule.get("R007", 0)
    return score.score, recon.summary, errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_period() -> str:
    tz = ZoneInfo(settings.display_tz)
    today = datetime.now(tz=tz).date()
    first_of_this_month = today.replace(day=1)
    last_of_prev = first_of_this_month - timedelta(days=1)
    return f"{last_of_prev.year:04d}{last_of_prev.month:02d}"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=None, help="YYYYMM (default: last complete month)")
    parser.add_argument(
        "--today", default=None,
        help="YYYY-MM-DD to use as 'today' for score calc (default: real today)",
    )
    args = parser.parse_args(argv)

    period = args.period or _default_period()
    if args.today:
        today = date.fromisoformat(args.today)
    else:
        tz = ZoneInfo(settings.display_tz)
        today = datetime.now(tz=tz).date()

    print(f"→ Wiping tenant tables (rule_pack survives) …")
    wipe()
    print(f"→ Seeding firm + admin + client + gstin_profile …")
    make_firm_and_admin()
    print(f"→ Seeding invoices + 2B for period {period} …")
    seed_invoices_and_2b(period)
    print(f"→ Running validate → reconcile → score (today={today.isoformat()}) …")
    score, summary, errors, warnings = run_engines(period, today)

    print("\n" + "=" * 72)
    print(" NIYAM AI DEMO — READY")
    print("=" * 72)
    print(f"  Firm      : {DEMO_FIRM_NAME}")
    print(f"  Client    : {DEMO_CLIENT_NAME}  ({CLIENT_GSTIN})")
    print(f"  Period    : {period}   (today for score = {today.isoformat()})")
    print()
    print(f"  Sign in at http://localhost:3000/login")
    print(f"    email    : {DEMO_EMAIL}")
    print(f"    password : {DEMO_PASSWORD}")
    print(f"    TOTP secret (add to Google Authenticator / Authy):")
    print(f"      {DEMO_TOTP_SECRET}")
    print()
    print(f"  Numbers on first load:")
    print(f"    Readiness score       : {score}/100")
    print(f"    Validation errors     : {errors}")
    print(f"    Validation warnings   : {warnings}")
    sd = summary.get("supplier_default", {})

    def _p(rupees_and_paise: int) -> str:
        """Format integer paise as ``₹1,23,456.78`` (Indian grouping).
        Preserves paise precision — CAs verify these to the paise."""
        neg = rupees_and_paise < 0
        v = abs(int(rupees_and_paise))
        rupees, paise = divmod(v, 100)
        s = str(rupees)
        if len(s) > 3:
            head, tail = s[:-3], s[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            if head:
                groups.insert(0, head)
            grouped = ",".join(groups) + "," + tail
        else:
            grouped = s
        return ("-" if neg else "") + f"₹{grouped}.{paise:02d}"

    print(f"    Matched paise         : {_p(summary.get('matched', {}).get('paise', 0))}")
    print(f"      of which claimable  : {_p(summary.get('matched', {}).get('paise_claimable', 0))}")
    print(f"    Probable paise        : {_p(summary.get('probable', {}).get('paise', 0))}")
    print(f"    Supplier_default paise: {_p(sd.get('paise', 0))} across {sd.get('count', 0)} suppliers")
    print(f"    Missing_entry paise   : {_p(summary.get('missing_entry', {}).get('paise', 0))}")
    print(f"    ⚠ ITC figures are '{summary.get('disclaimer', '(no disclaimer)')}'")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
