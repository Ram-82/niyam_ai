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
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}


type Options = {
  method?: string;
  body?: unknown;
  authenticated?: boolean;   // default true
  headers?: Record<string, string>;
};


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
    const detail =
      (parsed && typeof parsed === "object" && "detail" in (parsed as any)
        ? String((parsed as any).detail)
        : text) || res.statusText;
    throw new ApiError(res.status, detail, parsed);
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
    const detail =
      (parsed && typeof parsed === "object" && "detail" in (parsed as any)
        ? String((parsed as any).detail)
        : text) || res.statusText;
    throw new ApiError(res.status, detail, parsed);
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
