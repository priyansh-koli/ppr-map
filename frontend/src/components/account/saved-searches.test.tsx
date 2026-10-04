import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SessionProvider } from "@/components/auth/session";
import { SaveSearch } from "@/components/search/save-search";
import type { SavedSearch } from "@/lib/api/client";
import { ME, mockApi } from "@/test-fixtures/api";

import { SavedSearches } from "./saved-searches";
import { UnsubscribeAlert } from "./unsubscribe";

const nav = vi.hoisted(() => ({ query: "token=abc.def" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.query),
  usePathname: () => "/search",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

afterEach(() => vi.unstubAllGlobals());

const SAVED: SavedSearch = {
  id: "5b0f0f5e-0000-4000-8000-000000000001",
  name: "Carlow under 300k",
  query: { area: "carlow-1f4955", priceMax: "300000" },
  alertFrequency: "on_data_update",
  alertsActive: false,
  createdAt: "2026-09-30T10:00:00+00:00",
  lastAlertedAt: null,
  lastAlertMatches: null,
};

describe("SavedSearches", () => {
  it("warns that alerts wait for a confirmed email, and changes an alert", async () => {
    const { fetch } = mockApi({
      "GET /me": () => [200, { ...ME, emailVerified: false }],
      "GET /me/saved-searches": () => [200, [SAVED]],
      [`PATCH /me/saved-searches/${SAVED.id}`]: () => [200, { ...SAVED, alertFrequency: "weekly" }],
    });
    render(
      <SessionProvider>
        <SavedSearches />
      </SessionProvider>,
    );
    expect(await screen.findByRole("link", { name: SAVED.name })).toHaveAttribute(
      "href",
      "/search?area=carlow-1f4955&priceMax=300000",
    );
    expect(await screen.findByText(/not sent until you confirm your email/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute(
      "href",
      `/api/v1/me/saved-searches/${SAVED.id}/export.csv`,
    );
    fireEvent.change(screen.getByLabelText("Alert"), { target: { value: "weekly" } });
    await waitFor(() => expect(screen.getByLabelText("Alert")).toHaveValue("weekly"));
    const patch = fetch.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ alertFrequency: "weekly" });
  });
});

describe("UnsubscribeAlert", () => {
  it("asks before it switches the alert off", async () => {
    const { calls } = mockApi({ "POST /alerts/unsubscribe": () => [200, { name: "Mine" }] });
    render(<UnsubscribeAlert />);
    expect(calls("POST /alerts/unsubscribe")).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Stop these alerts" }));
    expect(await screen.findByText(/Alerts for .Mine. are off/)).toBeInTheDocument();
  });
});

describe("SaveSearch", () => {
  it("saves the search with the alert chosen", async () => {
    const { fetch } = mockApi({
      "GET /me": () => [200, ME],
      "POST /me/saved-searches": () => [201, SAVED],
    });
    render(
      <SessionProvider>
        <SaveSearch query={{ county: "carlow" }} suggestedName="Carlow" geolocated={false} />
      </SessionProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Save this search" }));
    expect(screen.getByLabelText("Name")).toHaveValue("Carlow");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    const post = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      name: "Carlow",
      query: { county: "carlow" },
      alertFrequency: "on_data_update",
    });
  });

  it("offers to save the next search after one is saved", async () => {
    const { calls } = mockApi({
      "GET /me": () => [200, ME],
      "POST /me/saved-searches": () => [201, SAVED],
    });
    const view = (query: Record<string, string>, name: string) => (
      <SessionProvider>
        <SaveSearch query={query} suggestedName={name} geolocated={false} />
      </SessionProvider>
    );
    const { rerender } = render(view({ county: "carlow", priceMax: "300000" }, "Carlow"));
    fireEvent.click(await screen.findByRole("button", { name: "Save this search" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    // The same filters in another order are the same search.
    rerender(view({ priceMax: "300000", county: "carlow" }, "Carlow"));
    expect(screen.getByText("Saved.")).toBeInTheDocument();
    rerender(view({ county: "kerry" }, "Kerry"));
    expect(screen.queryByText("Saved.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save this search" }));
    expect(screen.getByLabelText("Name")).toHaveValue("Kerry");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(calls("POST /me/saved-searches")).toBe(2);
  });
});
