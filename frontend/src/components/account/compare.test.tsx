import { act, render, screen, waitFor } from "@testing-library/react";

import { deferred, mockApi } from "@/test-fixtures/api";
import summary from "@/test-fixtures/summary-south-circular-road.json";

import { Compare } from "./compare";

const search = vi.hoisted(() => ({ ids: "" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(`ids=${search.ids}`),
}));

afterEach(() => vi.unstubAllGlobals());

describe("Compare", () => {
  it("lays saved properties side by side from the API", async () => {
    search.ids = summary.id;
    mockApi({ "GET /me/wishlist/compare": () => [200, [summary]] });
    render(<Compare />);
    await waitFor(() =>
      expect(screen.getByRole("columnheader", { name: summary.address })).toBeInTheDocument(),
    );
    expect(screen.getByRole("rowheader", { name: "Latest sale" })).toBeInTheDocument();
    expect(screen.getByText("€1,700,000")).toBeInTheDocument();
  });

  it("forgets a failure when the ids change", async () => {
    const slow = deferred<[number, unknown]>();
    mockApi({
      "GET /me/wishlist/compare": () =>
        search.ids === "fails"
          ? [422, { title: "Unprocessable", detail: "Compare 1 to 4" }]
          : slow.promise,
    });
    // A failure for one set of ids is not shown for the next.
    search.ids = "fails";
    const { rerender } = render(<Compare />);
    expect(await screen.findByText("Compare 1 to 4")).toBeInTheDocument();

    search.ids = summary.id;
    rerender(<Compare />);
    expect(screen.queryByText("Compare 1 to 4")).toBeNull();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    await act(async () => slow.resolve([200, [summary]]));
    expect(screen.getByRole("columnheader", { name: summary.address })).toBeInTheDocument();
  });

  it("ignores an answer that arrives after the ids changed", async () => {
    const first = deferred<[number, unknown]>();
    const other = { ...summary, id: "other", address: "1 Other Road" };
    mockApi({
      "GET /me/wishlist/compare": () => (search.ids === "stale" ? first.promise : [200, [other]]),
    });
    search.ids = "stale";
    const { rerender } = render(<Compare />);
    search.ids = "other";
    rerender(<Compare />);
    await screen.findByRole("columnheader", { name: other.address });
    await act(async () => first.resolve([200, [summary]]));
    expect(screen.queryByRole("columnheader", { name: summary.address })).toBeNull();
    expect(screen.getByRole("columnheader", { name: other.address })).toBeInTheDocument();
  });
});
