import { render, screen, waitFor } from "@testing-library/react";

import summary from "@/test-fixtures/summary-south-circular-road.json";

import { Compare } from "./compare";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(`ids=${summary.id}`),
}));

describe("Compare", () => {
  it("lays saved properties side by side from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify([summary]), { status: 200 })),
    );
    render(<Compare />);
    await waitFor(() =>
      expect(screen.getByRole("columnheader", { name: summary.address })).toBeInTheDocument(),
    );
    expect(screen.getByRole("rowheader", { name: "Latest sale" })).toBeInTheDocument();
    expect(screen.getByText("€1,700,000")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
