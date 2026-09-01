# Readiness P1 blockers

Items the readiness instrument has surfaced that block the bar:

> a CA provisioned by the vendor completes one client, one GSTIN, one period,
> from empty database to a filing marked filed, entirely in the browser.

An item leaves this list when a walkthrough run proves it, not when the code
looks right. Status is set from `walkthrough-run.log`, never from memory.

---

## P1-1 — The workspace default period has no 2B behind it

**Status:** OPEN. Blocks any claim that the readiness bar is met.

The workspace entry link builds its period from `previousCompletedPeriod()`
(`frontend/app/(app)/settings/page.tsx`), which resolves to the previous
completed month. The only mock 2B fixture for the walkthrough GSTIN is
`backend/app/gsp/fixtures/gstr2b_29ADVRS0000A1ZA_202607.json`.

So a CA who adds a GSTIN and clicks "Open workspace" today lands on a period
with no 2B data behind it and finds nothing there. The fixture set is pinned
to a fixed month while the product's default moves with the calendar; they
have already diverged.

**Why this is P1 and not a fixture chore.** The instrument currently follows
the fixture period for steps 6-13 and logs a `4.period-constraint` NOTE when
it differs from the product default. That is the instrument working around a
product characteristic, which is the thing the standing rule forbids. A green
run under this workaround proves the cycle closes on a period **no real user
lands on** — which is not the bar.

**Required before the bar can be called met:** either generate a mock 2B
fixture for the product's default period, or make the fixture set relative to
the current date, so the run exercises the path a customer actually takes.
Until then, a green walkthrough carries this caveat in its result section —
not a footnote.

**Do not** resolve this by changing the product's default period to match the
fixture. That would be fitting the product to the test.

---

## P1-2 — No browser affordance triggers a reconciliation run

**Status:** OPEN.

`POST /engines/reconcile` exists and is tested, but has zero frontend callers
(`frontend/` grep returns none). The reconciliation tab's empty state tells
the CA to "trigger a run" and then offers only a "Go to Imports" link
(`frontend/app/(app)/workspace/[gid]/page.tsx`). The cycle therefore cannot
be completed browser-only, which is the bar's own wording.

---

## P1-3 — Legal acceptance has no UI

**Status:** OPEN. Pre-pilot blocker.

`accepted_via='ui'` is reachable only via the API. `frontend/app/v2/legal/`
renders the hashed document read-only with no Accept control. The only caller
of `POST /legal/accept` in the repo is the Playwright bootstrap harness. The
`--auto-accept-legal` CLI flag writes `accepted_via='bootstrap'`, which is
provisioning and never evidence of consent — the flag hides the gap, it does
not close it.
