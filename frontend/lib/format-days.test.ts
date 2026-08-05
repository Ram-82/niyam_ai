import { describe, it, expect } from "vitest";
import { formatDaysToDue } from "./format-days";


describe("formatDaysToDue", () => {
  it("null -> empty dash", () => {
    expect(formatDaysToDue(null)).toEqual({ label: "—", tone: "empty" });
  });

  it("far horizon (> 3) -> plain number", () => {
    expect(formatDaysToDue(4)).toEqual({ label: "4", tone: "plain" });
    expect(formatDaysToDue(14)).toEqual({ label: "14", tone: "plain" });
    expect(formatDaysToDue(999)).toEqual({ label: "999", tone: "plain" });
  });

  it("1–3 days -> amber pill with singular/plural", () => {
    expect(formatDaysToDue(1)).toEqual({ label: "1 day", tone: "amber-pill" });
    expect(formatDaysToDue(2)).toEqual({ label: "2 days", tone: "amber-pill" });
    expect(formatDaysToDue(3)).toEqual({ label: "3 days", tone: "amber-pill" });
  });

  it("0 -> red pill 'Due today'", () => {
    expect(formatDaysToDue(0)).toEqual({ label: "Due today", tone: "red-pill" });
  });

  it("overdue -> red pill 'Overdue Nd'", () => {
    expect(formatDaysToDue(-1)).toEqual({ label: "Overdue 1d", tone: "red-pill" });
    expect(formatDaysToDue(-9)).toEqual({ label: "Overdue 9d", tone: "red-pill" });
    expect(formatDaysToDue(-42)).toEqual({ label: "Overdue 42d", tone: "red-pill" });
  });
});
