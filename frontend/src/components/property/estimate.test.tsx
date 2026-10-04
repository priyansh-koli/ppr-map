import { render, screen, within } from "@testing-library/react";

import type { Comparables, PriceEstimate } from "@/lib/api/client";
import nearBallinteer from "@/test-fixtures/comparables-ballinteer.json";
import nearSouthCircular from "@/test-fixtures/comparables-south-circular-road.json";
import ballinteer from "@/test-fixtures/estimate-ballinteer.json";
import southCircular from "@/test-fixtures/estimate-south-circular-road.json";

import { ComparableSales } from "./comparable-sales";
import { PriceEstimateCard } from "./price-estimate";

describe("PriceEstimateCard", () => {
  it("leads with the range, then says where it comes from", () => {
    render(<PriceEstimateCard estimate={ballinteer as PriceEstimate} />);
    expect(screen.getByText("€534,000 –").parentElement).toHaveTextContent("€534,000 – €961,000");
    expect(screen.getByText("Central figure €659,000.")).toBeInTheDocument();
    expect(screen.getByText(/Information, not a valuation/)).toBeInTheDocument();
    expect(screen.getByText(/its last market sale, €382,000 on/)).toHaveTextContent(
      "Dublin - houses index moved +72.4%",
    );
    expect(screen.getByText(/of 4,463 homes/)).toHaveTextContent(
      "7 or more years apart, 8 in 10 sold for between −18.9% and +46%",
    );
    expect(screen.getByText(/CC BY 4.0/)).toBeInTheDocument();
  });

  it("says why there is no estimate", () => {
    render(<PriceEstimateCard estimate={southCircular as PriceEstimate} />);
    expect(screen.getByText(/No index estimate/)).toHaveTextContent("sold in the last six months");
    expect(screen.queryByText(/€/)).toBeNull();
  });

  it("says when Ireland's range stands in for the region's", () => {
    const e = ballinteer as PriceEstimate;
    const pooled = { ...e, calibration: { ...e.calibration!, pooled: true } };
    render(<PriceEstimateCard estimate={pooled} />);
    expect(screen.getByText(/across Ireland/)).toHaveTextContent("too few such sales");
  });
});

describe("ComparableSales", () => {
  it("lists sales with links, how each was placed, and a link to the rest", () => {
    const c = nearSouthCircular as Comparables;
    render(<ComparableSales comparables={c} searchHref="/search?near=53.3,-6.27&radiusM=500" />);
    expect(screen.getByText(/165 market sales within 500 m/)).toHaveTextContent("€585,000");
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(c.items.length);
    const first = within(rows[0]!);
    expect(first.getByRole("link", { name: "33 South Circular Road, Dublin 8" })).toHaveAttribute(
      "href",
      "/property/55kv3gtv56mq",
    );
    expect(first.getByText("same street or place")).toBeInTheDocument();
    expect(first.getByText("50 m")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All sales within 500 m" })).toHaveAttribute(
      "href",
      "/search?near=53.3,-6.27&radiusM=500",
    );
  });

  it("says what the median is of, and gives none for fewer than 5 sales", () => {
    const c = nearSouthCircular as Comparables;
    const { rerender } = render(
      <ComparableSales comparables={{ ...c, medianN: 160 }} searchHref="/search" />,
    );
    expect(screen.getByText(/165 market sales/)).toHaveTextContent(
      "median €585,000 of the 160 filed with VAT",
    );
    rerender(
      <ComparableSales
        comparables={{ ...c, total: 6, medianN: 4, medianEur: null }}
        searchHref="/search"
      />,
    );
    expect(screen.getByText(/6 market sales/)).not.toHaveTextContent("median");
  });

  it("does not print 0 m for homes placed at the same street point", () => {
    render(<ComparableSales comparables={nearBallinteer as Comparables} searchHref="/search" />);
    expect(screen.getAllByText("same map point").length).toBeGreaterThan(0);
    expect(screen.queryByText("0 m")).toBeNull();
  });

  it("explains when a home is placed too roughly for comparables", () => {
    const c: Comparables = {
      available: false,
      reason: "This home is placed only at its town or area.",
      radiusM: 500,
      months: 24,
      total: 0,
      medianN: 0,
      items: [],
    };
    render(<ComparableSales comparables={c} searchHref="/search" />);
    expect(screen.getByText(/placed only at its town/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
