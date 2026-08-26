# Niyam AI — P2 shipping plan

P1 shipped the found-money engine end-to-end: purchase-register + GSTR-2B ingest, deterministic validation, 4-bucket reconciliation, filing-readiness score, filings JSON, CA dashboard, auth, invites, email + WhatsApp + narrator (mock modes), audit trail, per-firm rule packs, prod deployment docs.

P2 turns the "mock-mode P2 infrastructure already in the repo" into production capability, and adds the one genuinely-new capability that P1 skipped: OCR of PDF / photo invoices.

The same review-gate rule as P1 applies: **at the end of every step we run `pytest`, walk through the flow the step enables, and stop for CA sign-off before starting the next step.**

---

## What already exists (mock mode) vs. what P2 adds

| Track | Real module today | What P2 needs |
|---|---|---|
| GSP live pull | `app/gsp/*` — service, client, adapter_mock, crypto, lockout, retry, fixtures, local `MockGSPServer` | one live vendor adapter (Cygnet / TaxGenie / ClearTax / equivalent), sandbox creds, end-to-end sandbox test, live-mode ops runbook |
| LLM narrator | `app/narrator/*` — mock + Anthropic adapters, validator, hallucination retry | prod enablement: Anthropic key + `narrator_enabled=true` in a staging environment, cost + latency observation, per-firm feature flag |
| WhatsApp delivery | `app/whatsapp/*` — mock + Meta transport scaffolding, CA-approval gate, webhook signature | Meta WABA provisioning, template approval, first live send in staging, media-caching + rate-limit backoff |
| OCR invoice extraction | **nothing** — only a "stubbed" badge in settings | full track: adapter interface, mock + real (pdfminer + tesseract) adapters, `ocr_extraction` table, review UI, "accept → Invoice" flow |
| MSME mobile companion | **nothing** | Expo app for suppliers: log in via magic link, view chase requests, upload invoice photo / PDF, receive delivery confirmations |

---

## Step order

We build OCR first because it is the only unstarted capability with material CA-firm impact, doesn't require external vendor onboarding to prototype, and produces a testable slice with fixture PDFs. GSP-live + WhatsApp-live come next because they depend on vendor onboarding calendars (WABA is a multi-week bureaucratic pipeline; a GSP contract even longer). Narrator prod enablement is small enough to slot in anywhere it fits. Mobile is largest and depends on OCR being usable server-side, so it comes last.

### P2.1 — OCR invoice extraction

* **Step 1** (this session): module skeleton + mock adapter + `POST /ocr/invoice` + feature flag. No DB persistence, no real extractor — the extraction JSON is ephemeral. Review gate: does the extraction shape look right to a CA?
* **Step 2**: `ocr_extraction` table + Alembic migration + persistence + `GET /ocr/extractions` + `GET /ocr/extractions/{id}`. Adds append-only audit of every extraction attempt.
* **Step 3**: real extractor — text-native PDFs via `pdfminer.six`, scanned PDFs / photos via `tesseract`. Per-field confidence scoring.
* **Step 4**: `POST /ocr/extractions/{id}/accept` (materialises an `Invoice` row) and `POST /ocr/extractions/{id}/reject`.
* **Step 5**: frontend — upload widget on the workspace page, review card with low-confidence field highlighting, accept / reject / edit inline.
* **Step 6**: fixture-driven E2E — upload 5 sample PDFs, verify extraction quality bar (per-field accuracy > 90% on Niyam's canonical test set).

### P2.2 — GSP live-mode adapter

* **Step 1**: vendor selection call + contract kickoff (out of code scope).
* **Step 2**: write the live adapter behind the same `GSPClient` protocol the mock uses. Nothing else in the codebase changes — the swap is a single line in `service.get_adapter()`.
* **Step 3**: staging cutover behind `gsp_mode='live'`, sandbox creds, first real 2B pull end-to-end.
* **Step 4**: cost observability — dashboard rows for per-firm pull count and per-call price. Alert threshold on unexpected volume.

### P2.3 — WhatsApp live-mode delivery

* **Step 1**: Meta WABA provisioning + template approval (out of code scope, multi-week).
* **Step 2**: `transport_meta.py` end-to-end sandbox test — first real send to a Niyam-owned WhatsApp number.
* **Step 3**: rate-limit backoff + media-caching (Meta charges per template send but caches media by hash).
* **Step 4**: staging cutover behind `whatsapp_mode='meta'`, first real send to a pilot CA client's line.

### P2.4 — Narrator prod enablement

* **Step 1**: pilot firm gets `narrator_enabled=true` + `narrator_mode='anthropic'`. Anthropic key provisioned. Observe cost + latency on real 2-pagers.
* **Step 2**: prompt-cache tuning — the frozen `NarrationFacts` are re-generated per (firm, period); cache the system prompt to hit ~90% cache-read on regenerations.
* **Step 3**: per-firm on/off toggle in `settings/team` (some firms want vernacular narration, some don't).

### P2.5 — MSME mobile companion

* Scope: Expo (React Native) app for suppliers. Auth via magic-link SMS. Screens: (a) chase list, (b) invoice submit (photo + metadata form), (c) delivery confirmations.
* Depends on: P2.1 OCR (server extracts uploaded photos), P2.3 WhatsApp live (delivery confirmations).
* Broken out separately once the four server-side P2 tracks are green in staging.

---

## What stays out of P2

Notice assistant, advisory nudge engine, non-GSTR filings (GSTR-9 annual, GSTR-7 TDS), and multi-branch reconciliation are P4+ and remain out of scope.

Credit / debit note (CDN) handling in reconciliation is a **P1 domain-verification item** (see README "Domain verification needed") and stays on that track, not P2.
