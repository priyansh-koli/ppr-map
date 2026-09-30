import { fireEvent, render, screen, within } from "@testing-library/react";

import type { AreaStats, Distribution } from "@/lib/api/client";
import { mockApi } from "@/test-fixtures/api";

import { AreaTrends, periodLabel, PriceDistribution } from "./area-charts";
import { outlinePath } from "./area-outline";

afterEach(() => vi.unstubAllGlobals());

const point = (periodStart: string, n: number, median: number | null, provisional = false) => ({
  periodStart,
  n,
  median,
  p25: median ? median * 0.8 : null,
  p75: median ? median * 1.2 : null,
  provisional,
  suppressed: median === null,
});

const STATS: AreaStats = {
  area: { kind: "county", name: "Carlow", slug: "carlow" },
  periodKind: "rolling_12m",
  segment: "all",
  points: [
    point("2025-06-01", 40, 250000),
    point("2025-07-01", 3, null),
    point("2025-08-01", 42, 262000),
    point("2025-09-01", 44, 270000, true),
  ],
  national: [
    point("2025-06-01", 5000, 350000),
    point("2025-07-01", 5100, 355000),
    point("2025-08-01", 5200, 360000),
    point("2025-09-01", 4000, 362000, true),
  ],
};

describe("area charts", () => {
  it("labels periods by kind", () => {
    expect(periodLabel("quarter", "2025-04-01")).toBe("Q2 2025");
    expect(periodLabel("year", "2024-01-01")).toBe("2024");
    expect(periodLabel("rolling_12m", "2025-10-01")).toBe("12 months to Oct 2025");
  });

  it("draws the area against Ireland, with every value in the table", async () => {
    const { fetch } = mockApi({ "GET /areas/carlow/stats": () => [200, STATS] });
    render(
      <AreaTrends
        slug="carlow"
        name="Carlow"
        periodKinds={["month", "quarter", "rolling_12m", "year"]}
      />,
    );
    expect(
      await screen.findByRole("img", { name: /Median price, Carlow and Ireland/ }),
    ).toBeInTheDocument();
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("12 months to Sept 2025 (provisional)");
    expect(rows[2]).toHaveTextContent("fewer than 5"); // suppressed, not guessed
    expect(rows[2]).toHaveTextContent("€355,000");
    fireEvent.change(screen.getByLabelText("Periods"), { target: { value: "year" } });
    expect(String(fetch.mock.calls.at(-1)?.[0])).toContain("periodKind=year&segment=all");
  });

  it("hides price bands with fewer than 5 sales", async () => {
    const dist: Distribution = {
      area: { kind: "county", name: "Carlow", slug: "carlow" },
      windowStart: "2024-11-01",
      windowEnd: "2025-10-31",
      n: 30,
      bins: [
        { fromEur: 0, toEur: 100000, n: 0 },
        { fromEur: 100000, toEur: 200000, n: null },
        { fromEur: 200000, toEur: null, n: 27 },
      ],
      nationalShare: [0.05, 0.2, 0.75],
    };
    mockApi({ "GET /areas/carlow/distribution": () => [200, dist] });
    render(<PriceDistribution slug="carlow" name="Carlow" />);
    expect(await screen.findByText("<5 sales")).toBeInTheDocument();
    expect(screen.getByText("90.0%")).toBeInTheDocument();
    expect(
      screen.getByLabelText(/€100K–€200K: fewer than 5 sales; Ireland 20.0%/),
    ).toBeInTheDocument();
  });

  it("outlines a polygon inside its box", () => {
    const d = outlinePath(
      {
        type: "Polygon",
        coordinates: [
          [
            [-7, 52],
            [-6, 52],
            [-6, 53],
            [-7, 52],
          ],
        ],
      },
      [-7, 52, -6, 53],
      100,
    );
    expect(d.startsWith("M")).toBe(true);
    const numbers = d.match(/-?\d+(\.\d+)?/g)!.map(Number);
    expect(Math.min(...numbers)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...numbers)).toBeLessThanOrEqual(100);
    expect(outlinePath({ type: "Point", coordinates: [0, 0] }, [0, 0, 1, 1], 100)).toBe("");
  });
});
