import { render, screen } from "@testing-library/react";

import type { PropertySummary } from "@/lib/api/client";
import summary from "@/test-fixtures/summary-south-circular-road.json";

import { HoverCard } from "./hover-card";

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
    const { rerender } = render(<HoverCard content={{ kind: "cell", n: 3, median: 250000 }} />);
    expect(screen.queryByRole("button", { name: "Close details" })).toBeNull();
    rerender(<HoverCard content={{ kind: "cell", n: 3, median: 250000 }} onClose={() => {}} />);
    expect(screen.getByRole("button", { name: "Close details" })).toBeInTheDocument();
  });
});
