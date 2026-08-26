# Niyam AI Narrator — Data Security Explainer

**Audience**: CA firms considering enabling LLM narration for their
clients, and clients asking their CA about the AI usage on their
GST reports.

**One-paragraph summary**: The Niyam narrator uses a Large Language
Model (LLM) to draft one page of prose in a 2-page GST filing
summary. **The LLM sees only pre-aggregated financial totals plus
your firm name and one client trade name** — no invoice numbers, no
counterparty details, no PANs, no auth tokens. Every number the LLM
writes is validated against the original figures before the CA sees
the draft. **The CA reviews and can edit every narration before it
reaches the client.** LLM narration is **off by default per firm** —
a firm admin opts in explicitly and can turn it off at any time.

---

## What the LLM sees

Exactly this shape of pre-aggregated block. Example for one filing:

```
LANGUAGE: English (en)
CLIENT: Beta Traders                     ← trade name only, no PAN
CA FIRM: Acme CA
PERIOD: 202607
RETURN TYPE: GSTR1
READINESS SCORE: 65
DAYS TO DUE: 5

SALES: ₹1,00,00,000
PURCHASES: ₹50,00,000
MARGIN: ₹50,00,000

TAX PAID: ₹25,00,000
TAX DUE: ₹30,00,000

ITC — matched: ₹2,50,00,000
ITC — probable: ₹1,50,00,000
ITC — supplier_default: ₹43,00,000 (6 suppliers)
ITC — missing register entries: ₹1,20,00,000

TOP BLOCKERS (owner in parens):
  - ITC at risk from 6 suppliers [₹43,00,000] (ca)
```

That is the entire input. The LLM's only job is to render that block
into 2–3 sentences per section in the chosen language.

## What the LLM does NOT see

Under any circumstance, the LLM never receives:

- **Individual invoice records** — no invoice numbers, no line items, no dates
- **Counterparty GSTINs or PANs** — only counts and aggregate totals
- **Contact details** — no phone numbers, email addresses, physical addresses
- **Buyer or supplier trade names** — only your firm's name + the ONE
  client trade name currently being narrated
- **Auth or session data** — no JWTs, GSTN tokens, GSP session keys, or
  passwords ever touch the narrator subsystem
- **Raw GSTR-2B / GSTR-1 payloads** — these are parsed by deterministic
  code that stays inside the Niyam infrastructure
- **Rule pack contents** — only the version identifier is passed through
- **Any data from any other firm or client** — RLS blocks cross-firm
  reads at the database layer, before the narrator subsystem is even
  invoked

The narrator has no access to the database itself. The service layer
builds the facts block from validated internal state, hands the block
to the adapter, and receives back text.

## The safety net — the validator

Every response from the LLM passes through a **number validator**
before the CA sees the draft:

1. All numeric values in the LLM's prose are extracted (rupee amounts,
   percentages, counts, years).
2. Each value is checked against the frozen facts block.
3. **If even one number appears in the prose that is not in the facts,
   the draft is discarded automatically.** The narrator retries once
   with a stricter reminder appended to the prompt. If it happens
   again, the CA sees "narration failed — regenerate" — never
   fabricated numbers.

This means the LLM cannot "round to the nearest thousand", "compute a
percentage that isn't in the facts", or invent a supplier count. It
can only rephrase what is already there.

## Who reviews the output

**The CA reviews every narration before the client sees it.**
The workflow is:

1. CA triggers narration generation via the Delivery panel.
2. Draft prose appears in a review pane; CA can edit any of the four
   blocks (page1_health, page1_tax_position, page2_attention,
   page2_ask_your_ca).
3. Only after CA approval does the narration attach to the 2-page
   report that goes to the client.

There is no direct LLM-to-client path. The CA is always in the loop.

## Provider policies

The narrator supports multiple LLM providers, selected per-deployment:

### Anthropic (Claude models)

- **Training on API data**: By default, Anthropic does not train models
  on API traffic. Enterprise Data Processing Agreements (DPAs) reinforce
  this contractually. See
  https://www.anthropic.com/legal/aup for the current terms.
- **Region**: US.
- **Retention**: 30 days for safety monitoring, then deleted (per
  Anthropic's stated policy — verify current terms at contract time).
- **Certifications**: SOC 2 Type II. GDPR-compliant DPA available.

### Google Gemini

- **Training on API data**: The paid tier (Vertex AI / paid API key)
  does not train on customer data. **The free-tier Gemini API MAY use
  submitted prompts for improving models** — read Google's current
  terms before using free-tier for real client data.
- **Region**: Multi-region; India region available via Vertex AI.
- **Certifications**: SOC 2, ISO 27001, HIPAA (paid tier). Free tier
  does not carry enterprise certifications.

### Mock (template — no external call)

- No API traffic. No data leaves the Niyam infrastructure.
- Output quality lower than the LLM options.
- Recommended for firms with strict data-locality requirements OR for
  demo environments.

## Per-firm control

**LLM narration is OFF by default for every firm.** A firm admin who
wants to opt in flips a single toggle in `Settings → Firm preferences`.
They can flip it back at any time; the change takes effect immediately
on the next narration request.

If a specific client of yours objects to LLM use even after seeing this
document, keep the firm-level narrator toggle OFF — the report will use
template narration and be functionally identical, just with less prose
polish.

## Audit trail

Every LLM call is logged to `narrator_call_log`:

- Firm ID (RLS-scoped)
- Provider (`anthropic` / `gemini` / `mock`)
- Model ID (e.g. `claude-haiku-4-5-20251001`)
- Attempt number (1 for first call, 2 for retry after validator failure)
- Language (`en` / `hi` / `kn` / `mr`)
- Success / failure + failure reason
- Token counts (input, output, cache-read, cache-creation)
- Latency (ms)
- Timestamp

The log is APPEND ONLY — Postgres triggers refuse UPDATE and DELETE
even from a database superuser. This gives you a defensible record of
exactly which client data went to which model, when.

## Cost

Cost is deliberately **not** the reason to pick a provider — at pilot
scale (~1,200 narrations per firm per year), a full year of Anthropic
Opus 4.7 is roughly ₹6,000. Haiku 4.5 is roughly ₹400. Gemini free tier
is ₹0.

The reasons to pick one over another are:

- **Data residency**: Gemini (Vertex AI, India region) if you need
  in-country processing.
- **Vernacular quality**: Anthropic Claude models produce the best
  Hindi / Kannada / Marathi we have benchmarked, per informal
  observation on our sample data. Gemini is close. Test on your own
  clients before committing.
- **Certifications you need to show**: Anthropic and Gemini paid tier
  both hold SOC 2. Gemini free tier does not.
- **Vendor risk**: Adding both providers means either can be swapped
  in ~30 minutes if one has an outage or policy change.

## What we do NOT do

To pre-empt questions:

- We do not use the LLM for tax advisory. It never opines on whether a
  filing is compliant, or predicts what GSTN will do.
- We do not use the LLM for any numeric computation. Every rupee figure
  in the report comes from deterministic engines.
- We do not send LLM-generated text to any client without CA approval.
- We do not use client-name substitution to hide identity from the LLM.
  We use the real client trade name in the facts block — the tradeoff
  we made is aggregation over pseudonymization. If your firm wants
  pseudonymization instead, tell us; it's a small config change.

## Contact

Questions about this document: reach the CA firm admin, who can
escalate to Niyam AI support. Firm-level opt-in / opt-out for LLM
narration is under `Settings → Firm preferences → LLM narration`.

---
*Last reviewed: 2026-08-12. Verify provider terms independently — the
LLM landscape moves fast and this document may lag by weeks.*
