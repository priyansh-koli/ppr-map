import { fireEvent, render, screen, within } from "@testing-library/react";

import { ThemeToggle } from "@/components/ui/theme-toggle";
import type { Overview } from "@/lib/api/client";
import { mockApi } from "@/test-fixtures/api";

import { Counties } from "./counties";
import { MonthlyChart } from "./monthly-chart";

afterEach(() => vi.unstubAllGlobals());

const OVERVIEW: Overview = {
  dataVersion: "2026-09-18.r1",
  totalSales: 807724,
  totalProperties: 728460,
  firstSaleDate: "2010-01-01",
  windowStart: "2025-08-01",
  windowEnd: "2026-07-01",
  monthly: [
    { month: "2026-06-01", sales: 5100, provisional: false },
    { month: "2026-07-01", sales: 5356, provisional: false },
    { month: "2026-08-01", sales: 4288, provisional: true },
    { month: "2026-09-01", sales: 1992, provisional: true },
  ],
  counties: [
    { slug: "dublin", name: "Dublin", sales: 17891, medianPriceEur: 480000, lat: 53.4, lng: -6.28 },
    { slug: "leitrim", name: "Leitrim", sales: 3, medianPriceEur: null, lat: 54.1, lng: -8.0 },
  ],
};

describe("home page overview", () => {
  beforeEach(() => mockApi({ "GET /stats/overview": () => [200, OVERVIEW] }));

  it("says which months are provisional, in the chart and in its table", async () => {
    render(<MonthlyChart />);
    expect(await screen.findByText("10,456")).toBeInTheDocument(); // June + July, complete only
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent)).toEqual([
      "Sept 20261,992Provisional",
      "Aug 20264,288Provisional",
      "Jul 20265,356Complete",
      "Jun 20265,100Complete",
    ]);
  });

  it("links each county to the map and never shows a median for too few sales", async () => {
    render(<Counties />);
    const dublin = await screen.findByRole("link", { name: /Dublin/ });
    expect(dublin).toHaveAttribute("href", "/map?lat=53.4000&lng=-6.2800&z=9");
    expect(dublin).toHaveTextContent("€480K");
    expect(screen.getByRole("link", { name: /Leitrim/ })).toHaveTextContent("too few sales");
  });
});

describe("ThemeToggle", () => {
  afterEach(() => {
    delete document.documentElement.dataset.theme;
    localStorage.clear();
  });

  it("cycles device, light, dark and remembers the choice", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /Theme: same as this device/ });
    fireEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("ppr-theme")).toBe("light");
    fireEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.click(button);
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(localStorage.getItem("ppr-theme")).toBeNull();
  });
});
