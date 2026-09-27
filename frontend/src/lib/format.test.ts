import { formatDate, formatDateTime, formatDistance, formatEur, tileDate } from "./format";

describe("formatting", () => {
  it("formats euro amounts for Ireland", () => {
    expect(formatEur(1700000)).toBe("€1,700,000");
    // Money can arrive as a decimal string.
    expect(formatEur("1700000.00")).toBe("€1,700,000");
  });

  it("formats timestamps, and shows anything unparseable as it came", () => {
    expect(formatDateTime("2026-09-27T10:00:00+00:00")).toMatch(/27 Sept 2026/);
    expect(formatDateTime("not a date")).toBe("not a date");
  });

  it("reads ISO dates as calendar dates", () => {
    expect(formatDate("2026-09-18")).toBe("18 Sept 2026");
    expect(tileDate(20260918)).toBe("2026-09-18");
  });

  it("rounds distances", () => {
    expect(formatDistance(32)).toBe("30 m");
    expect(formatDistance(1530)).toBe("1.5 km");
  });
});
