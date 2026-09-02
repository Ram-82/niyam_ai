import { describe, it, expect } from "vitest";
import { ApiError } from "./api";
import { formatApiError } from "./format-api-error";


describe("formatApiError", () => {
  it("never returns \"[object Object]\" for a structured detail", () => {
    // The exact shape backend returned that produced the CI failure.
    const err = new ApiError(
      403,
      "legal_acceptance_required",
      {
        detail: {
          error: "legal_acceptance_required",
          pending: [
            { doc_type: "terms", version: "1.0.0", content_hash: "abc" },
          ],
        },
      },
      null,
      "req-e2e-1234",
      "legal_acceptance_required",
    );
    const out = formatApiError(err);
    expect(out).not.toContain("[object Object]");
    expect(out).not.toBe("");
  });

  it("uses the known-code message for legal_acceptance_required", () => {
    const err = new ApiError(
      403,
      "legal_acceptance_required",
      null,
      null,
      null,
      "legal_acceptance_required",
    );
    expect(formatApiError(err)).toMatch(/accept.*Terms.*DPA|accept.*Data Processing/i);
  });

  it("appends the request id when there is no known-code branch", () => {
    const err = new ApiError(500, "internal", null, null, "req-abc-123", null);
    expect(formatApiError(err)).toContain("req-abc-123");
    expect(formatApiError(err)).toContain("500");
  });

  it("degrades safely for a bare object throwable", () => {
    // A caller who throws `{ oops: true }` should not surface [object Object].
    const out = formatApiError({ oops: true });
    expect(out).not.toContain("[object Object]");
    expect(out).toBe("Unknown error");
  });

  it("uses Error.message for ordinary Errors", () => {
    expect(formatApiError(new Error("boom"))).toBe("boom");
  });

  it("handles a raw string throwable", () => {
    expect(formatApiError("something failed")).toBe("something failed");
  });

  it("handles ApiError without a request id", () => {
    const err = new ApiError(422, "invalid_gstin", null);
    const out = formatApiError(err);
    expect(out).toContain("422");
    expect(out).toContain("invalid_gstin");
    expect(out).not.toContain("req");
  });
});
