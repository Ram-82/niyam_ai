# Walkthrough purchase register fixture

`walkthrough-register.csv` is the purchase register the walkthrough uploads at
step 7. It exists so the reconciliation and filing steps have a known-good
target to assert against.

**Contents:** one purchase invoice.

* `invoice_number = INV-A1`
* `invoice_date = 2026-07-05`
* `taxable_value = 1000.01` (paise not paise — rupees, the parser converts)
* `total = 1180.01`
* `counterparty_gstin = 29PPPPP0000A1ZP`

**Expected reconciliation:** matches the `INV-A1` entry under supplier
`29PPPPP0000A1ZP` in the mock GSP 202607 GSTR-2B fixture
(`backend/app/gsp/fixtures/gstr2b_29ADVRS0000A1ZA_202607.json` — labeled A1
"1-paise difference in taxable value (should still match, tolerance=100p)").

**Expected match bucket:** `matched` — one row.

**Why this specific pair:** the mock 2B fixture for period 202607 is the
adversarial one, so it has ten deliberately-tricky invoices to break the
matcher. INV-A1 is the closest to a "clean match" (only a 1-paise taxable
delta, well inside the 100-paise tolerance the rule pack allows). Using it
means the walkthrough proves the golden path works without depending on the
matcher's edge-case handling. Everything else in that fixture is intentionally
harder.

**Not for demo.** This fixture matches the adversarial GSTR-2B; the ITC
figure asserted by the walkthrough is meaningful only for that mock. It does
not prove the cycle closes against real GSTN — that requires real credentials
and is out of scope until pilot handoff.
