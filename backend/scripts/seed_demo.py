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

    Bucket             Rows  ₹ total   Purpose
    matched              10   2,50,000  cleanly reconciled ITC
    probable              2   1,50,000  live confirm demo
    supplier_default      6      43,000  the "₹43,000 at risk" headline
      (2 with near-misses, 4 without — both review states visible)
    missing_entry         1   1,20,000  the fat unrecorded purchase
    (also: 3 R001-only invoices ₹57,000 with NULL counterparty — not
     part of recon, but seed validation errors for the invoices tab)

  Total register value ₹5,00,000. Sum of supplier_default rows equals
  the headline ₹43,000 exactly — CAs WILL do that arithmetic in their
  head at a demo.

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


def seed_invoices_and_2b(period: str) -> None:
    """The main story. All amounts in PAISE (multiply rupees by 100)."""
    year, month = int(period[:4]), int(period[4:])
    d5 = date(year, month, 5)
    d10 = date(year, month, 10)
    d15 = date(year, month, 15)
    d20 = date(year, month, 20)
    d25 = date(year, month, 25)

    pull_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        # ----- Register: 10 matched, ₹2,50,000 -----
        # Two invoices per matched-supplier, matching amounts each.
        # 5 suppliers × 2 invoices × ₹25,000 = ₹2,50,000.
        matched_invoices = []
        for sup_key, sup_gstin in [
            ("M_1", SUPPLIERS["M_1"]),
            ("M_2", SUPPLIERS["M_2"]),
            ("M_3", SUPPLIERS["M_3"]),
            ("M_4", SUPPLIERS["M_4"]),
            ("M_5", SUPPLIERS["M_5"]),
        ]:
            for i, dt in enumerate([d10, d20], start=1):
                num = f"INV-{sup_key}-{i}"
                # ₹25,000 total = ₹21,186 taxable + ₹1,907 cgst + ₹1,907 sgst
                # (18% intra-state slab, rounded).
                cgst = sgst = 190_700  # paise
                taxable = 21_18_600
                matched_invoices.append(
                    (num, dt, sup_gstin, taxable, cgst, sgst)
                )
                _insert_invoice(
                    conn, num=num, dt=dt, cp=sup_gstin,
                    taxable=taxable, cgst=cgst, sgst=sgst,
                )

        # Flag one matched invoice with an R005 (intra-state IGST) — a
        # common "wrong tax head" error. Override via bound params
        # (Postgres rejects Python-style underscored numeric literals
        # inside SQL text).
        conn.execute(
            text(
                "UPDATE invoice SET cgst_paise = 0, sgst_paise = 0, "
                "igst_paise = :igst, total_paise = :total "
                "WHERE gstin_profile_id = :g AND invoice_number = :num"
            ),
            {
                "g": DEMO_GID,
                "num": "INV-M_3-1",
                "igst": 381_400,
                "total": 25_00_000,
            },
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

        # ----- Register: 2 probable, ₹1,50,000 -----
        _insert_invoice(
            conn, num="INV-P_1-1", dt=d15, cp=SUPPLIERS["P_1"],
            taxable=63_55_900, cgst=5_72_050, sgst=5_72_050,
        )
        _insert_invoice(
            conn, num="INV-P_2-1", dt=d15, cp=SUPPLIERS["P_2"],
            taxable=63_55_900, cgst=0, sgst=0, igst=11_44_100,
        )

        # ----- Register: 6 supplier_defaults, ₹43,000 -----
        # Amounts chosen so sum = 43,000 exactly (criterion #2).
        # ₹18,000 + ₹8,500 + ₹5,000 + ₹4,500 + ₹4,000 + ₹3,000 = ₹43,000
        sd_specs = [
            ("INV-SD_1-1", d5,  SUPPLIERS["SD_1"], 18_00_000, "998311"),
            ("INV-SD_2-1", d10, SUPPLIERS["SD_2"],  8_50_000, None),      # R004
            ("INV-SD_3-1", d15, SUPPLIERS["SD_3"],  5_00_000, "998311"),
            ("INV-SD_4-1", d20, SUPPLIERS["SD_4"],  4_50_000, "998311"),
            ("INV-SD_5-1", d25, SUPPLIERS["SD_5"],  4_00_000, None),      # R004
            ("INV-SD_6-1", d15, SD_6_MALFORMED,     3_00_000, "998311"),  # R002
        ]
        for num, dt, cp, total_paise, hsn in sd_specs:
            _insert_invoice(
                conn, num=num, dt=dt, cp=cp,
                taxable=total_paise, cgst=0, sgst=0, hsn=hsn,
            )

        # ----- Register: 3 R001-only invoices, ₹57,000 -----
        # Missing counterparty_gstin → won't appear in recon (query
        # filters IS NOT NULL) but will surface R001 errors.
        for i, dt in enumerate([d5, d15, d25], start=1):
            _insert_invoice(
                conn, num=f"INV-NOGSTIN-{i}", dt=dt, cp=None,
                taxable=19_00_000, cgst=0, sgst=0, hsn="998311",
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
        # For each matched register invoice, insert a matching 2B entry
        # (same key + same total; intra-state → CGST+SGST).
        for num, dt, sup, taxable, cgst, sgst in matched_invoices:
            _insert_b2b(
                conn, pull_id=pull_id, sup=sup, num=num, dt=dt,
                taxable=taxable, cgst=cgst, sgst=sgst,
            )

        # Probable: slight drift in date + amount vs register.
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["P_1"],
            num="INV/P_1-1",  # normalizes same as INV-P_1-1
            dt=d15 + timedelta(days=2),
            taxable=63_60_000, cgst=5_72_400, sgst=5_72_400,  # +~₹200 on total
        )
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["P_2"],
            num="INV-P_2/1",
            dt=d15 + timedelta(days=2),
            taxable=63_60_000, cgst=0, sgst=0, igst=11_45_000,
        )

        # Near-miss 2B entries for SD_2 and SD_4 — same supplier, same
        # normalized number, but amount well outside fuzzy tolerance so
        # they don't fuzzy-match. Pass 3 surfaces them as near-misses
        # AND (per engine design) also as missing_entry residuals since
        # near-misses don't consume the 2B row. Kept tiny (₹5, ₹3) so
        # the missing_entry paise headline stays dominated by the real
        # fat GHOST entry below.
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["SD_2"],
            num="INV-SD_2-1", dt=d10,
            taxable=500,   # ₹5 — trivially small
        )
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["SD_4"],
            num="INV-SD_4-1", dt=d20,
            taxable=300,   # ₹3 — trivially small
        )

        # The fat missing_entry — 2B has a big invoice from a supplier
        # the client never recorded.
        _insert_b2b(
            conn, pull_id=pull_id, sup=SUPPLIERS["MISSING"],
            num="INV-GHOST-BIG", dt=d15,
            taxable=1_20_00_000,  # ₹1,20,000
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
    print(f"    Matched paise         : ₹{summary.get('matched', {}).get('paise', 0) // 100:,}")
    print(f"    Probable paise        : ₹{summary.get('probable', {}).get('paise', 0) // 100:,}")
    print(f"    Supplier_default paise: ₹{sd.get('paise', 0) // 100:,} across {sd.get('count', 0)} suppliers")
    print(f"    Missing_entry paise   : ₹{summary.get('missing_entry', {}).get('paise', 0) // 100:,}")
    print(f"    ⚠ ITC figures are '{summary.get('disclaimer', '(no disclaimer)')}'")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
