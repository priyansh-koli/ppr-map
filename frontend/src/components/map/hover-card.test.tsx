import { fireEvent, render, screen } from "@testing-library/react";

import type { PropertySummary } from "@/lib/api/client";
import summary from "@/test-fixtures/summary-south-circular-road.json";

import { HoverCard } from "./hover-card";
import type { SalePoint } from "./layers";

const SPOT: SalePoint[] = [
  { id: "a", price: 410000, date: 20260301, lngLat: [-6.27, 53.33] },
  { id: "b", price: 385000, date: 20250110, lngLat: [-6.27, 53.33] },
];

describe("HoverCard", () => {
  it("shows a real hover summary with its sources' caveats", () => {
    render(
      <HoverCard
        content={{ kind: "property", id: summary.id, summary: summary as PropertySummary }}
      />,
    );
    expect(screen.getByText("49 South Circular Road, Dublin 8")).toBeInTheDocument();
    expect(screen.getByText("€1,700,000")).toBeInTheDocument();
    expect(screen.getByText(/Earlier: €1,425,000 \(2022\)/)).toBeInTheDocument();
    expect(screen.getByText(/Stop: Victoria Street/)).toBeInTheDocument();
    expect(screen.getByText("Straight-line distances.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /full sale history/i })).toHaveAttribute(
      "href",
      `/property/${summary.id}`,
    );
  });

  it("says when sales only have an approximate location", () => {
    render(
      <HoverCard content={{ kind: "stack", n: 12, median: 310000, confidence: "locality" }} />,
    );
    expect(screen.getByText("12 sales at an approximate location")).toBeInTheDocument();
    expect(screen.getByText(/Only its town, village or townland/)).toBeInTheDocument();
  });

  it("offers a close button only when pinned", () => {
    const { rerender } = render(<HoverCard content={{ kind: "cell", n: 3, median: null }} />);
    expect(screen.queryByRole("button", { name: "Close details" })).toBeNull();
    rerender(<HoverCard content={{ kind: "cell", n: 3, median: null }} onClose={() => {}} />);
    expect(screen.getByRole("button", { name: "Close details" })).toBeInTheDocument();
  });

  it("gives no median for a group of fewer than 5 sales", () => {
    render(<HoverCard content={{ kind: "stack", n: 3, median: null, confidence: "locality" }} />);
    expect(screen.getByText("Fewer than 5 sales: no median")).toBeInTheDocument();
    expect(screen.queryByText(/€/)).toBeNull();
  });

  it("says a zoomed-out group zooms in when clicked", () => {
    render(<HoverCard content={{ kind: "cell", n: 24, median: 310000 }} />);
    expect(screen.getByText("24 sales here")).toBeInTheDocument();
    expect(screen.getByText("Median €310,000")).toBeInTheDocument();
    expect(screen.getByText(/Click to zoom in/)).toBeInTheDocument();
  });

  it("counts sales on one spot while hovering, and lists them to choose from once pinned", () => {
    const onChoose = vi.fn();
    const { rerender } = render(
      <HoverCard content={{ kind: "spot", sales: SPOT, addresses: null }} />,
    );
    expect(screen.getByText("2 sales at this spot")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /€410,000/ })).toBeNull();

    rerender(
      <HoverCard
        content={{ kind: "spot", sales: SPOT, addresses: null }}
        onClose={() => {}}
        onChoose={onChoose}
      />,
    );
    expect(screen.getAllByText("Loading address…")).toHaveLength(2);

    rerender(
      <HoverCard
        content={{ kind: "spot", sales: SPOT, addresses: { a: "4 Synge Street, Dublin 8" } }}
        onClose={() => {}}
        onChoose={onChoose}
      />,
    );
    expect(screen.getByText("Address not listed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /4 Synge Street/ }));
    expect(onChoose).toHaveBeenCalledWith(SPOT[0]);
  });
});
