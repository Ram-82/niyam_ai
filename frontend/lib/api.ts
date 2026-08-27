/**
 * Thin fetch wrapper. Auto-attaches the Bearer token from localStorage.
 * On 401, clears the token and returns the failure to the caller — the
 * page-level auth guard decides whether to redirect.
 */
import { clearAccessToken, getAccessToken } from "./auth";

const BASE =
  (typeof process !== "undefined" && process.env.NIYAM_API_BASE) ||
  (typeof window !== "undefined"
    ? (window as any).NIYAM_API_BASE || "http://localhost:8000"
    : "http://localhost:8000");


export class ApiError extends Error {
  status: number;
  body: unknown;
  // Parsed from the ``Retry-After`` response header, in seconds. Only
  // populated for 429 responses that carry the header — else ``null``.
  // Used by the UI to render a wall-clock retry time; see
  // ``lib/format-retry-after.ts`` and ``RATE_LIMIT_COPY``.
  retryAfterSeconds: number | null;
  // ``X-Request-Id`` from the response, echoed back from
  // ``app.observability`` middleware. Rendered on failure surfaces so a
  // reporter can hand it back and we can find the log line.
  requestId: string | null;
  // Machine-readable slug when the backend returns
  // ``{"detail": {"error": "<slug>", ...}}``. UI branches on this rather
  // than pattern-matching on the human message.
  code: string | null;
  constructor(
    status: number,
    message: string,
    body: unknown,
    retryAfterSeconds: number | null = null,
    requestId: string | null = null,
    code: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.body = body;
    this.retryAfterSeconds = retryAfterSeconds;
    this.requestId = requestId;
    this.code = code;
  }
}


type Options = {
  method?: string;
  body?: unknown;
  authenticated?: boolean;   // default true
  headers?: Record<string, string>;
};


/**
 * Normalise the backend's error shape into (code, message).
 *
 * The backend returns one of three shapes:
 *   1. ``{"detail": "human string"}``            — legacy / simple cases
 *   2. ``{"detail": {"error": "<slug>", ...}}``  — machine-readable code
 *   3. Non-JSON text                             — 5xx unhandled, upstream, etc.
 *
 * For (2) we return a short, factual message keyed off the slug. Never
 * String()-coerce a non-string detail — that's the origin of the
 * "[object Object]" defect the UI used to show.
 */
function extractErrorParts(
  parsed: unknown,
  fallbackText: string,
  statusText: string,
): { code: string | null; message: string } {
  if (parsed && typeof parsed === "object" && "detail" in (parsed as any)) {
    const detail = (parsed as any).detail;
    if (typeof detail === "string") {
      return { code: null, message: detail };
    }
    if (detail && typeof detail === "object" && typeof detail.error === "string") {
      return { code: detail.error, message: detail.error };
    }
    // Detail is a structured object without a string ``error`` — fall
    // through to statusText rather than String()-coerce.
    return { code: null, message: statusText || "Request failed" };
  }
  return {
    code: null,
    message: fallbackText || statusText || "Request failed",
  };
}


function requestIdFrom(res: Response): string | null {
  return res.headers.get("X-Request-Id");
}


function retryAfterFrom(res: Response): number | null {
  const hdr = res.headers.get("Retry-After");
  return hdr && /^\d+$/.test(hdr) ? Number(hdr) : null;
}


export async function api<T = unknown>(
  path: string,
  opts: Options = {}
): Promise<T> {
  const {
    method = "GET",
    body,
    authenticated = true,
    headers: extraHeaders = {},
  } = opts;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
  if (authenticated) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (res.status === 401 && authenticated) {
    clearAccessToken();
  }

  const text = await res.text();
  const parsed = text ? safeJson(text) : null;

  if (!res.ok) {
    const { code, message } = extractErrorParts(parsed, text, res.statusText);
    throw new ApiError(
      res.status,
      message,
      parsed,
      retryAfterFrom(res),
      requestIdFrom(res),
      code,
    );
  }
  return parsed as T;
}


/**
 * Multipart form uploads. Separate function so the Content-Type header
 * doesn't get overridden by the JSON default above.
 */
export async function apiFormData<T = unknown>(
  path: string,
  form: FormData
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    body: form,
  });
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (!res.ok) {
    const { code, message } = extractErrorParts(parsed, text, res.statusText);
    throw new ApiError(
      res.status,
      message,
      parsed,
      retryAfterFrom(res),
      requestIdFrom(res),
      code,
    );
  }
  return parsed as T;
}


function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}


/**
 * Fetch a binary resource (e.g. PDF preview) with the auth header
 * attached. Returns a Blob the caller can turn into an object URL for
 * ``window.open`` or a download link.
 *
 * On non-2xx: throws ApiError with the response body as text (best
 * effort — a binary endpoint that 500s often returns JSON error).
 */
export async function apiBlob(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { method: "GET", headers });
  if (res.status === 401) {
    clearAccessToken();
  }
  if (!res.ok) {
    const txt = await res.text();
    const parsed = txt ? safeJson(txt) : null;
    const { code, message } = extractErrorParts(parsed, txt, res.statusText);
    throw new ApiError(
      res.status,
      message,
      parsed,
      null,
      requestIdFrom(res),
      code,
    );
  }
  return res.blob();
}
