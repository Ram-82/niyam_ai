# v2 wiring audit — corrected

**Correction date:** 2026-08-27
**Supersedes:** an earlier E-series report that claimed "GSP, WhatsApp, and supplier-chase write paths are FULLY WIRED" and "the surface audit was wrong." That earlier claim was itself wrong: it confused the *legacy* `frontend/app/(app)/workspace/[gid]` tree with the *v2* `frontend/app/v2/**` tree.

The Playwright specs at `frontend/e2e/gsp.spec.ts`, `whatsapp.spec.ts`, and `supplier-chase.spec.ts` all navigate to `/workspace/{gid}?...`, not `/v2/*`. They exercise the legacy tree. The panels they drive (`components/ConnectionsPanel.tsx`, `DeliveryPanel.tsx`, `SupplierChasePanel.tsx`, `OcrPanel.tsx`, `FilingsTab.tsx`) are only imported from `frontend/app/(app)/workspace/[gid]/page.tsx` — grep across `frontend/app/v2` finds zero importers.

So P1's actual UI reality is a two-headed frontend:

* **Legacy** at `/workspace/{gid}` — full write surface, e2e-tested, is the actual working UI today.
* **v2** at `/v2/**` — screen ports of the 17 Figma mockups, mostly READ-side wired. Missing most write actions.

This doc catalogues what each surface can and cannot do so future planning is not built on the earlier wrong claim.

---

## Wiring status by path

Status meanings:
* **WIRED** — button/UI exists AND its handler calls a real backend endpoint.
* **DEAD** — button/UI exists but the handler is disabled, missing, or a placeholder toast.
* **ABSENT** — no UI in this surface at all.

Rows are sorted worst → best.

| # | Path | v2 status | Legacy status | Where in v2 | Where in legacy |
|---|---|---|---|---|---|
| 1 | Add GSTIN | ABSENT | WIRED | — | `frontend/app/(app)/workspace/[gid]/page.tsx` client + gstin add flow |
| 2 | Invoice upload (register) | ABSENT | WIRED | — | `frontend/app/(app)/imports/` |
| 3 | 2B (GSTR-2B) JSON upload | ABSENT | WIRED | — | `frontend/app/(app)/imports/` |
| 4 | GSP connect / consent / pull | ABSENT | WIRED | — | `frontend/components/ConnectionsPanel.tsx` → `POST /gsp/consent` (line 68), `/gsp/consent/confirm` (line 95), `/gsp/pull` (line 128), `/gsp/disconnect` (line 151) |
| 5 | OCR extract | ABSENT | WIRED | contracts page reads `/ocr/extractions` but no kickoff button | `frontend/components/OcrPanel.tsx` |
| 6 | OCR accept | DEAD | WIRED | contracts page has a "Mark reviewed" placeholder | `frontend/components/OcrPanel.tsx` |
| 7 | Filing generate | ABSENT | WIRED | `useFilingMutations` at `frontend/app/v2/(app)/filings/useFilingsData.ts:234` exposes approve / mark-filed / unlock only — no generate | `frontend/components/FilingsTab.tsx` |
| 8 | Reconciliation match confirm | ABSENT | WIRED | no `/reconciliation` folder under `v2/(app)/` | `frontend/app/(app)/workspace/[gid]?tab=reconciliation` |
| 9 | Reconciliation match reject | ABSENT | WIRED | — | ditto |
| 10 | Reconciliation flag resolve | ABSENT | WIRED | — | ditto |
| 11 | Report send (WhatsApp) | ABSENT | WIRED | — | `frontend/components/DeliveryPanel.tsx` → `POST /whatsapp/delivery-requests` → `/approve` → `/send` |
| 12 | Supplier chase | ABSENT | WIRED | — | `frontend/components/SupplierChasePanel.tsx` → `POST /match-results/{id}/mark-near-miss-reviewed` → `/supplier-contacts` → `/whatsapp/delivery-requests/chase` → `/approve` → `/send` |
| 13 | Rule pack activate | ABSENT | ABSENT | — | — (backend endpoints exist, no UI in either tree) |
| 14 | Legal acceptance (POST) | ABSENT | ABSENT | `v2/legal/legal-page.tsx` is a read-only doc viewer, `useEffect` only fetches; no accept button | no accept button in legacy either — the gate blocks writes but the UI to accept is not built |
| 15 | Firm switcher (multi-firm active-firm picker) | ABSENT | ABSENT | user model has single `firm_id` (not a membership table); no switcher UI in either tree | — |
| 16 | Narrator budget view / set | ABSENT | ABSENT | — | — |
| 17 | Create client (single, non-CSV) | DEAD | WIRED | `v2/(app)/clients/page.tsx` "Add client" button exists but has no onClick | `frontend/app/(app)/settings/` invite/user flow includes client add |
| 18 | CSV import (clients) | WIRED | WIRED | `v2/onboarding/useCsvImport.ts` → `POST /clients/import?dry_run={bool}` | onboarding also runs the legacy path |
| 19 | Filing approve | WIRED | WIRED | `useFilingMutations` (line 263) → `POST /filings/{id}/approve` | `frontend/components/FilingsTab.tsx` |
| 20 | Filing mark-filed | WIRED | WIRED | `useFilingMutations` (line 264) → `POST /filings/{id}/mark-filed` | ditto |
| 21 | Filing unlock | WIRED | WIRED | `useFilingMutations` (line 266) → `POST /filings/{id}/unlock` | ditto |

Twelve of the twenty-one paths are ABSENT in v2. Two are DEAD. Four are WIRED. Three are WIRED via a shared onboarding/settings path but the v2 surface itself is thin.

---

## Read-side wiring in v2 (working, tested)

To be fair to the v2 port, its READ surface is real and healthy:

* Dashboard: `firm/health-summary`, `command-center`, `filings`, `reports/timeliness`, activity — via `useDashboardData`.
* Clients list: `/clients`, `/command-center`, `/calendar/upcoming` — via `useClientsData`.
* Filings list + detail: `/filings`, `/filings/{id}`, `/gstins/{id}/readiness` — via `useFilingsData`.
* Calendar, reports, audit log, settings, contracts, ai-assistant, onboarding — all fetch real endpoints. Every hook now routes errors through `formatApiError` after the F2 fix, so `[object Object]` cannot escape.
* Legal pages `/v2/legal/terms` and `/v2/legal/dpa` render `/legal/documents/{doc_type}` verbatim so a viewer sees the same bytes the acceptance flow would hash. Just no accept button.

---

## Consequences for planning

* **The 17-mockup v2 port is READ-mostly, not read-and-write.** The claim "v2 port of all 17 mockups solid" is accurate only in the "screens render with real data" sense. It is not accurate in the "a CA can complete a filing cycle here" sense.
* **The Phase E slice list built on the earlier surface-audit claim needs re-scoping** — with 12 ABSENT and 2 DEAD paths in v2, the P1 filing walkthrough (F4) is not doable in v2 alone. It requires either the legacy `/workspace` surface, or v2 growing the missing handlers first.
* **Legal accept is missing from both surfaces.** The gate blocks writes with `legal_acceptance_required` — but neither v2 nor legacy has a UI to complete the acceptance. Something else (backend fixture, bootstrap script, or a page not yet grepped) must be filling the gap during e2e runs. Verify before assuming a real firm could get past first login without operator help.

---

## Method for reproduction

Every WIRED/DEAD/ABSENT verdict above came from grepping `frontend/app/v2/**` and `frontend/app/(app)/**` for:

* the endpoint URL under `api(` calls,
* explicit onClick or button handlers,
* imports of `frontend/components/*Panel.tsx` handlers.

The Playwright specs at `frontend/e2e/*.spec.ts` were re-read to confirm they navigate to `/workspace/...` and not `/v2/...` — that is the observation that flipped the earlier claim. If a later change reroutes those specs to `/v2/*`, this doc becomes obsolete and the wiring picture flips.
