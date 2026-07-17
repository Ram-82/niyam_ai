/**
 * Token storage — localStorage for P1 dev/demo.
 *
 * Production hardening tracked in the README: switch to httpOnly
 * SameSite=Strict cookies + a lightweight anti-CSRF header. For P1
 * demos the localStorage path is fine and keeps the login flow
 * transparent when debugging in dev tools.
 */

const KEY = "niyam.access_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}

export function setAccessToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, token);
}

export function clearAccessToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
}
