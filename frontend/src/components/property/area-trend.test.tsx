import { render, screen } from "@testing-library/react";

import type { PropertyDetail } from "@/lib/api/client";
import property from "@/test-fixtures/property-south-circular-road.json";

import { AreaTrend } from "./area-trend";

type Series = NonNullable<PropertyDetail["areaSeries"]>;
const series = property.areaSeries as Series;

describe("AreaTrend", () => {
  it("draws the real series with provisional months dashed, and a table view", () => {
    const { container } = render(<AreaTrend series={series} />);
    expect(screen.getByRole("img", { name: /Dublin city and suburbs/ })).toBeInTheDocument();
    expect(container.querySelector("polyline[stroke-dasharray]")).not.toBeNull();
    expect(screen.getAllByRole("row")).toHaveLength(series.points.length + 1);
  });

  it("shows suppressed months as gaps, never as numbers", () => {
    const points = series.points.map((p, i) =>
      i === 3 ? { ...p, n: 4, median: null, suppressed: true } : p,
    );
    render(<AreaTrend series={{ ...series, points }} />);
    expect(screen.getByText("not shown (fewer than 5)")).toBeInTheDocument();
  });
});
