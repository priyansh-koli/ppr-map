import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { SearchResults, Suggestion } from "@/lib/api/client";
import { mockApi } from "@/test-fixtures/api";

import { PlaceSearch } from "./place-search";
import { SearchPage } from "./search-page";

const nav = vi.hoisted(() => ({ query: "", replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.query),
  usePathname: () => "/search",
  useRouter: () => ({ replace: nav.replace, push: nav.push }),
}));
// MapLibre needs WebGL; the list is what these tests read.
vi.mock("./results-map", () => ({ ResultsMap: () => <div data-testid="results-map" /> }));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  nav.replace.mockReset();
  nav.push.mockReset();
});

const CARLOW: Suggestion = {
  kind: "settlement",
  label: "Carlow",
  detail: "Co. Carlow · town",
  slug: "carlow-1f4955",
};
const RESULTS: SearchResults = {
  items: [
    {
      id: "p1",
      address: "178 Pollerton Road, Carlow",
      confidence: "street",
      lat: 52.83,
      lng: -6.92,
      latestSale: {
        date: "2025-11-03",
        priceEur: 240000,
        isNew: false,
        flags: { notFullMarketPrice: false, vatExclusive: false, bulk: false },
      },
      nSales: 2,
      change: { previousDate: "2015-06-01", previousPriceEur: 160000, changePct: 50 },
    },
  ],
  total: 1,
  page: 1,
  pageSize: 25,
  bbox: [-6.93, 52.82, -6.91, 52.84],
  query: { area: "carlow-1f4955" },
  places: [{ kind: "settlement", name: "Carlow", slug: "carlow-1f4955" }],
};

describe("PlaceSearch", () => {
  it("suggests places from our own data and picks one with the keyboard", async () => {
    const { fetch } = mockApi({ "GET /geocode/autocomplete": () => [200, [CARLOW]] });
    const chosen = vi.fn();
    render(<PlaceSearch onSelect={chosen} />);
    const box = screen.getByRole("combobox");
    fireEvent.change(box, { target: { value: "carl" } });
    const option = await screen.findByRole("option", { name: /Carlow/ });
    expect(option).toHaveAttribute("aria-selected", "true");
    expect(String(fetch.mock.calls[0]?.[0])).toContain("/api/v1/geocode/autocomplete?q=carl");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(chosen).toHaveBeenCalledWith(CARLOW);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("does not ask for one letter", async () => {
    const { calls } = mockApi({ "GET /geocode/autocomplete": () => [200, []] });
    render(<PlaceSearch onSelect={() => {}} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "c" } });
    await new Promise((r) => setTimeout(r, 300));
    expect(calls("GET /geocode/autocomplete")).toBe(0);
  });
});

describe("SearchPage", () => {
  it("lists the matches with their price change and the places searched", async () => {
    nav.query = "area=carlow-1f4955&sort=-change";
    const { fetch } = mockApi({
      "GET /meta": () => [200, { dataVersion: "v1", tilesVersion: "v1" }],
      "GET /search": () => [200, RESULTS],
    });
    render(<SearchPage />);
    expect(await screen.findByRole("link", { name: "178 Pollerton Road, Carlow" })).toHaveAttribute(
      "href",
      "/property/p1",
    );
    expect(screen.getByRole("heading", { name: "1 property" })).toBeInTheDocument();
    expect(screen.getByText("+50%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Carlow" })).toBeInTheDocument();
    const call = fetch.mock.calls.find(([u]) => String(u).includes("/search?"));
    expect(String(call?.[0])).toContain("area=carlow-1f4955&sort=-change&pageSize=25");
    expect(screen.getByRole("link", { name: "Open on the map" }).getAttribute("href")).toMatch(
      /^\/map\?area=carlow-1f4955&lat=52\.83/,
    );

    fireEvent.click(screen.getByRole("button", { name: "Remove Carlow" }));
    expect(nav.replace).toHaveBeenCalledWith("/search?sort=-change", { scroll: false });
  });

  it("changes the sort through the URL", async () => {
    nav.query = "";
    mockApi({
      "GET /meta": () => [200, { dataVersion: "v1", tilesVersion: "v1" }],
      "GET /search": () => [200, { ...RESULTS, places: [] }],
    });
    render(<SearchPage />);
    await screen.findByRole("heading", { name: "1 property" });
    fireEvent.change(screen.getByRole("combobox", { name: "Sort" }), {
      target: { value: "price" },
    });
    expect(nav.replace).toHaveBeenCalledWith("/search?sort=price", { scroll: false });
  });

  it("says when the filters cannot be used", async () => {
    nav.query = "county=cork";
    mockApi({
      "GET /meta": () => [200, { dataVersion: "v1", tilesVersion: "v1" }],
      "GET /search": () => [429, { title: "Too Many Requests" }],
    });
    render(<SearchPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many searches in a minute");
  });

  it("asks for the location only after the button is pressed", async () => {
    nav.query = "";
    mockApi({
      "GET /meta": () => [200, { dataVersion: "v1", tilesVersion: "v1" }],
      "GET /search": () => [200, RESULTS],
    });
    const getCurrentPosition = vi.fn((ok: PositionCallback) =>
      ok({ coords: { latitude: 52.8312, longitude: -6.9271 } } as GeolocationPosition),
    );
    vi.stubGlobal("navigator", { ...navigator, geolocation: { getCurrentPosition } });
    render(<SearchPage />);
    await screen.findByRole("heading", { name: "1 property" });
    expect(getCurrentPosition).not.toHaveBeenCalled();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Near my location" })),
    );
    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith(
        "/search?near=52.83120%2C-6.92710&radiusM=1000&nearSource=geolocation",
        { scroll: false },
      ),
    );
  });
});
