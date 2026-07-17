import { describe, expect, it } from "vitest";
import { formatPaise, formatRupeesRounded, toBigIntPaise } from "./format";


describe("formatPaise", () => {
  it("formats zero", () => {
    expect(formatPaise(0)).toBe("₹0.00");
  });

  it("formats sub-rupee", () => {
    expect(formatPaise(50)).toBe("₹0.50");
    expect(formatPaise(99)).toBe("₹0.99");
  });

  it("formats hundreds of rupees", () => {
    expect(formatPaise(4320050)).toBe("₹43,200.50");
  });

  it("uses Indian grouping for lakhs", () => {
    // ₹1,23,456.78
    expect(formatPaise(12345678)).toBe("₹1,23,456.78");
  });

  it("uses Indian grouping for crores — the acceptance-criterion test", () => {
    // ₹1,23,45,678.90 — value above 1 crore, guaranteed by criterion #6
    expect(formatPaise(1234567890)).toBe("₹1,23,45,678.90");
  });

  it("uses Indian grouping for tens of crores", () => {
    // 12,34,56,789 rupees = 12,345,678,900 paise
    expect(formatPaise(12345678900n)).toBe("₹12,34,56,789.00");
    // 12 arab: 12,34,56,78,900 rupees = 12,345,678,900,00 paise
    expect(formatPaise("1234567890000")).toBe("₹12,34,56,78,900.00");
  });

  it("handles negatives (rare but should not crash)", () => {
    expect(formatPaise(-100)).toBe("-₹1.00");
    expect(formatPaise(-12345678)).toBe("-₹1,23,456.78");
  });

  it("accepts bigint, number, and numeric string equivalently", () => {
    expect(formatPaise(1234567890)).toBe("₹1,23,45,678.90");
    expect(formatPaise(1234567890n)).toBe("₹1,23,45,678.90");
    expect(formatPaise("1234567890")).toBe("₹1,23,45,678.90");
  });

  it("rejects fractional numbers — no float leaks", () => {
    expect(() => formatPaise(1.5)).toThrow(/integer paise/);
  });

  it("rejects garbage strings", () => {
    expect(() => formatPaise("banana")).toThrow(/integer paise/);
    expect(() => formatPaise("1.5")).toThrow(/integer paise/);
  });

  it("stays precise past 2^53 paise (float would lose it)", () => {
    // 2^53 = 9007199254740992; add 100 paise more — a Number cast would
    // round this to the nearest representable double.
    const beyondSafe = 9007199254740992n + 100n; // ₹9,00,71,99,25,47,410.92
    expect(formatPaise(beyondSafe)).toBe("₹9,00,71,99,25,47,410.92");
  });
});


describe("formatRupeesRounded", () => {
  it("rounds ₹43,200.50 up to ₹43,201", () => {
    expect(formatRupeesRounded(4320050)).toBe("₹43,201");
  });

  it("rounds ₹43,200.49 down to ₹43,200", () => {
    expect(formatRupeesRounded(4320049)).toBe("₹43,200");
  });

  it("above 1 crore, still Indian-grouped", () => {
    expect(formatRupeesRounded(1234567890)).toBe("₹1,23,45,679");
  });
});


describe("toBigIntPaise", () => {
  it("passes bigints through", () => {
    expect(toBigIntPaise(42n)).toBe(42n);
  });
  it("converts safe integer numbers", () => {
    expect(toBigIntPaise(42)).toBe(42n);
  });
  it("parses digit strings", () => {
    expect(toBigIntPaise("42")).toBe(42n);
  });
});
