"""PDF rendering — the CA-branded MSME 2-pager.

The narrator gives us the four prose blocks; this module assembles them
plus the numeric snapshot into an HTML page and hands it to WeasyPrint
for a PDF. The output is what the WhatsApp send actually attaches, and
what the CA previews at /narrator/runs/{id}/pdf before approving delivery.

Design invariants:
* Every rupee figure that appears in the PDF is either (a) copied
  verbatim from ``narration_run.facts`` (deterministic, engine-produced)
  or (b) part of the narrator's approved prose blocks (which have
  already gone through the validator). The template does NOT compute
  numbers.
* The rendered PDF is branded to the CA firm — the firm_name is the
  letterhead. "Niyam AI" appears once, small, in the attribution
  footer only.
* Every ITC figure carries "before credit/debit note adjustments"
  visibly, matching the on-screen contract from step 9.
"""
