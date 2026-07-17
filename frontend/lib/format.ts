/**
 * Money formatting for Niyam AI.
 *
 * Backend sends money as integer paise. UI displays as ₹ with Indian
 * digit grouping (last three digits, then pairs) — e.g., ₹1,23,45,678.90.
 *
 * Rules the CA sales pitch depends on:
 *   1. No floating-point math. We use BigInt throughout so values above
 *      2^53 paise (~₹90,000 crore) still format correctly. Integer paise
 *      from the API can lose precision the moment it hits Number in
 *      JavaScript for sums / diffs across a large firm's history.
 *   2. One formatter. Every ITC display in the app calls formatPaise().
 *      No local re-implementations. Grep should return this file only.
 *   3. Every ITC figure is accompanied by CDN_DISCLAIMER — see constants.ts.
 *      This formatter is deliberately silent on the disclaimer so callers
 *      can position it in the right visual affordance (tooltip, footnote,
 *      badge). It is the caller's responsibility.
 */

export const RUPEE = "₹";

/**
 * Format an integer paise amount as an Indian-grouped rupee string.
 *
 *   formatPaise(4320050)     -> "₹43,200.50"
 *   formatPaise(1234567890)  -> "₹1,23,45,678.90"
 *   formatPaise(0)           -> "₹0.00"
 *   formatPaise(-100)        -> "-₹1.00"
 *   formatPaise("999999999") -> "₹99,99,999.99"
 *
 * Accepts number, bigint, or a numeric string. Rejects fractional
 * numbers (paise are integers — a decimal input means someone rupees'd
 * where they should have paise'd).
 */
export function formatPaise(paise: number | bigint | string): string {
  const big = toBigIntPaise(paise);
  const negative = big < 0n;
  const abs = negative ? -big : big;
  const rupees = abs / 100n;
  const frac = abs % 100n;
  const grouped = indianGroup(rupees.toString());
  const fracStr = frac.toString().padStart(2, "0");
  return `${negative ? "-" : ""}${RUPEE}${grouped}.${fracStr}`;
}

/**
 * Same as formatPaise() but rounds to whole rupees. Used in dense
 * tables where the paise digits waste horizontal space and the ₹
 * amounts are large (crores).
 */
export function formatRupeesRounded(paise: number | bigint | string): string {
  const big = toBigIntPaise(paise);
  const negative = big < 0n;
  const abs = negative ? -big : big;
  // Round to nearest rupee.
  const rupees = (abs + 50n) / 100n;
  return `${negative ? "-" : ""}${RUPEE}${indianGroup(rupees.toString())}`;
}

/**
 * Convert a bare bigint / number / string to an integer-paise BigInt.
 * Throws on anything that isn't an integer — no silent float coercion.
 */
export function toBigIntPaise(v: number | bigint | string): bigint {
  if (typeof v === "bigint") return v;
  if (typeof v === "number") {
    if (!Number.isInteger(v)) {
      throw new Error(
        `formatPaise expected integer paise, got fractional number ${v}`
      );
    }
    return BigInt(v);
  }
  const s = String(v).trim();
  if (!/^-?\d+$/.test(s)) {
    throw new Error(`formatPaise expected integer paise string, got ${JSON.stringify(v)}`);
  }
  return BigInt(s);
}

/**
 * Indian digit grouping on a numeric-string of rupees.
 *   "123"        -> "123"
 *   "1234"       -> "1,234"
 *   "12345"      -> "12,345"
 *   "123456"     -> "1,23,456"
 *   "12345678"   -> "1,23,45,678"
 *   "123456789"  -> "12,34,56,789"
 */
function indianGroup(rupeeStr: string): string {
  if (rupeeStr.length <= 3) return rupeeStr;
  const tail = rupeeStr.slice(-3);
  let head = rupeeStr.slice(0, -3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head.length > 0) groups.unshift(head);
  return groups.join(",") + "," + tail;
}
