import { formatDate, formatDistance, formatEur, tileDate } from "./format";

describe("formatting", () => {
  it("formats euro amounts for Ireland", () => {
    expect(formatEur(1700000)).toBe("€1,700,000");
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
