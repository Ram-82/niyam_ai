# WhiteBooks GSP — API contract reference

Source of truth for the `adapter_whitebooks.py` implementation.
Extracted from the WhiteBooks-supplied Postman collection
(`WB-GST-API.postman_collection.json`, 2025-05-15) and the
GST-API-Error-Codes.docx (296 codes). Where the collection is silent
(all 494 documented responses are 404/500 skeletons — no success body
is captured), we infer from the GSTN public contract.

## 1. Base URL & auth model

- **Sandbox base URL**: `https://apisandbox.whitebooks.in` (confirmed
  from the "Choose the environment" panel on the WhiteBooks portal).
- **Production base URL**: TBD — swap when we buy a production
  subscription (portal → "Production" tab). Config prefix stays the
  same.
- **Auth**: header-based. Every authenticated request carries:
  - `client_id` — issued by WhiteBooks (per app)
  - `client_secret` — issued by WhiteBooks (per app)
  - `gst_username` — the taxpayer's GSTN portal login (e.g.
    `TN_NT2.152383` in sandbox)
  - `state_cd` — first 2 chars of the GSTIN
  - `ip_address` — public IP of our calling server (GSTN whitelist)
  - `txn` — the per-session `auth_token` returned by
    `/authentication/authtoken`. Empty on the first call.
- **NO** `Authorization: Bearer` header. **NO** OAuth. **NO** mTLS
  (the collection has zero certificate references).
- **Content-Type**: `application/json` when a body is sent.

Sandbox OTP is fixed at **`575757`** (per collection description on
`/authentication/authtoken`).

## 2. Authentication endpoints

All under `/authentication/`. All are `GET`. Query params are
passed on the URL; auth-context values above are in headers.

| Endpoint | Purpose | Query | Notes |
|---|---|---|---|
| `/authentication/otprequest` | Trigger OTP delivery | `email` | No body |
| `/authentication/authtoken` | Exchange OTP for session | `email`, `otp` | Response carries `auth_token` (opaque) → use as `txn` on every subsequent call. TTL not explicit in docs; GSTN contract is 6h. |
| `/authentication/refreshtoken` | Extend session | `email` | Sends current `txn` header |
| `/authentication/logout` | Invalidate `txn` | `email` | |
| `/authentication/otpforevc` | OTP for e-verification code filing (NOT session auth) | `email`, `gstin`, `pan`, `form_type` | Only used inside submit/file flows — irrelevant to 2B pull |

**Response bodies not documented.** Working assumption (industry
standard):

```json
// /authentication/otprequest → 200
{ "status_cd": "1", "status_desc": "OTP has been sent successfully" }

// /authentication/authtoken → 200
{
  "status_cd": "1",
  "auth_token": "<opaque-string>",
  "expiry": "6h",
  "sek": "<base64-AES-key>"   // present iff encryption is on
}
```

If encryption is on, `sek` is RSA-encrypted with the app's public key
at onboarding — decrypt with our private key to get an AES-256 session
key used to decrypt every subsequent payload. **Deferred** — try clear
first, add layer only on `RET191166` errors.

## 3. GSTR-2B fetch — 3-step async

WhiteBooks does NOT expose a single-shot fetch. The flow:

### 3.1 `PUT /gstr2b/gen2b` — request generation

| Location | Name | Example |
|---|---|---|
| header | `gstin` | `29ABCDE1234F1Z5` |
| header | `ret_period` | `072025` (MMYYYY) |
| header | (all auth headers) | |
| header | `Content-Type: application/json` | |
| query | `email` | |
| body | `{}` (empty JSON object, required) | |

Response (inferred):
```json
{ "status_cd": "1", "int_tran_id": "abc..." }
```

### 3.2 `GET /gstr2b/get2b` — poll status

| Location | Name |
|---|---|
| query | `gstin`, `int_tran_id`, `email` |
| header | (all auth headers) |

Status codes surfaced in response body (per error-codes.docx):
- `RTN_24` — generation in progress, retry with backoff
- `RTN_31` — file generated, safe to call `/gstr2b/all`
- `RTN_32` — request already in progress
- `RTN_25` — generation failed

### 3.3 `GET /gstr2b/all` — fetch payload

| Location | Name |
|---|---|
| query | `gstin`, `rtnprd` (MMYYYY), `email` |
| query | `filenum` (optional, when payload chunked) |
| header | (all auth headers) |

Response envelope (inferred from GSTN public 2B contract — WhiteBooks
passes GSTN through unchanged):

```json
{
  "chksum": "<sha256>",
  "data": {
    "rtnprd": "072025",
    "gstin": "29ABCDE1234F1Z5",
    "gendt": "14-08-2025",
    "docdata": {
      "b2b":  [ ... ],
      "b2ba": [ ... ],
      "cdnr": [ ... ],
      "cdnra":[ ... ],
      "impg": [ ... ],
      "impgsez": [ ... ]
    },
    "itcsumm": { ... },
    "otitcsum":{ ... }
  }
}
```

Our existing `app.ingestion.gstr2b_parser.parse_gstr2b_json` accepts
this shape verbatim — no reshape needed in the adapter.

## 4. Error code translation

Mapping to our `GSPErrorKind` taxonomy:

| WhiteBooks code | Our kind |
|---|---|
| `RET13509` (OTP expired or incorrect) | Ambiguous — treat as `OTP_INVALID` unless context suggests expiry. Default: `OTP_INVALID`. |
| `RET11407` AUTH Token invalid | `SESSION_EXPIRED` |
| `RET11408` Invalid Transaction ID | `SESSION_EXPIRED` |
| `RET11402` Unauthorized User | `SESSION_EXPIRED` (whitelist / cred issue — needs reconnect) |
| `RET191166` Decryption failed | `UNKNOWN` — flags that we need to enable payload encryption |
| `RET191101`, `RET191139` Decrypt failed / decoded null | `UNKNOWN` — same as above |
| `RET13504` System try again | `GSTN_UNAVAILABLE` (also our rate-limit stand-in — GSTN has no dedicated code) |
| `RET13505` System Failure | `GSTN_UNAVAILABLE` |
| `RET11400` Header missing | `UNKNOWN` (programmer error, not user) |
| `RET11409` Username invalid | `SESSION_EXPIRED` |
| `RET11410` Invalid GSTIN | `UNKNOWN` |
| `RTN_24`, `RTN_32` In progress | Not errors — poll continues |
| `RTN_31` Ready | Not an error — trigger fetch |
| `RTN_25` Generation failed | `GSTN_UNAVAILABLE` |
| `RTN_27` Not a normal taxpayer | `UNKNOWN` |
| `RET13508` No details found | `UNKNOWN` (empty 2B is legitimate — parser handles) |
| HTTP 429 without body code | `RATE_LIMITED` |
| HTTP 401/403 without body code | `SESSION_EXPIRED` |
| HTTP 5xx without body code | `GSTN_UNAVAILABLE` |

### Observed in-wild but NOT in the docx

| Code | Message | Cause | Kind |
|---|---|---|---|
| `AUTH4037` | "API access is not available or user expiry Duration is less than or equal to auth token expiry duration" | Sandbox API access is not activated on the WhiteBooks subscription side. Fixed by WhiteBooks Support enabling the sandbox flag on the account. | `UNKNOWN` — mapping to `SESSION_EXPIRED` would misroute the CA into a reconnect loop that cannot succeed until an operator escalates. |

## 5. Notes / gotchas

1. **Header naming is inconsistent between endpoints**:
   - `gen2b` uses `ret_period` (header)
   - `all` uses `rtnprd` (query)
   - Both mean the same thing (MMYYYY). The adapter normalises.
2. **`state_cd` is duplicative** — it's the first 2 chars of the
   GSTIN. Adapter extracts it, no config value needed.
3. **`ip_address` header** — GSTN whitelists GSP-provided IPs. In
   sandbox this is more permissive; in prod it MUST match the IP
   registered in the WhiteBooks portal. Config setting
   `GSP_IP_ADDRESS` — deploy warns loudly if empty in `live` mode.
4. **`email` query param** — the DEVELOPER email registered on the
   WhiteBooks portal, NOT the taxpayer's email. Comes from
   `GSP_DEVELOPER_EMAIL`.
5. **No path-parameter GSTIN** — GSTIN goes in a query on GETs and a
   header on `gen2b`. Watch the split.
6. **Session TTL** — 6 hours per GSTN spec; not carried in the response.
   Adapter defaults to `6 * 3600` when unspecified.
7. **Encryption**: `sek` + AES-256 payload encryption is a GSTN
   standard. Deferred — first real call will show whether sandbox
   enforces it. If `RET191166` appears, layer in
   `adapter_whitebooks_crypto.py` (public/private key + AES helpers).
8. **No `Retry-After` header** — for `RATE_LIMITED` / `GSTN_UNAVAILABLE`,
   fall back to the retry policy in `app.gsp.retry`.

## 6. Config wiring

`.env` (or docker-compose env for the api service):

```
GSP_MODE=whitebooks
GSP_BASE_URL=https://apisandbox.whitebooks.in
GSP_CLIENT_ID=<from-portal-Credentials>
GSP_CLIENT_SECRET=<from-portal-Credentials>
GSP_GST_USERNAME=<taxpayer-portal-username>   # e.g. TN_NT2.152383
GSP_IP_ADDRESS=<public-IP-of-api-server>
GSP_DEVELOPER_EMAIL=<email-registered-on-whitebooks-portal>
```

`GSP_API_KEY` is NOT used in whitebooks mode. The validator relaxes
the requirement when `gsp_mode='whitebooks'` and enforces the six
values above instead.
