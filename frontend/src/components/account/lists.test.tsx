import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { View, WishlistItem } from "@/lib/api/client";
import { deferred, mockApi } from "@/test-fixtures/api";

import { History } from "./history";
import { Wishlist } from "./wishlist";

afterEach(() => vi.unstubAllGlobals());

const ITEM = {
  id: 7,
  kind: "property",
  propertyId: "abc",
  areaSlug: null,
  title: "49 South Circular Road, Dublin 8",
  note: null,
  createdAt: "2026-09-27T10:00:00+00:00",
  // Money may come as a decimal string; it must read the same as a number.
  latestPriceEur: "1700000.00" as unknown as WishlistItem["latestPriceEur"],
  latestSaleDate: "2025-03-14",
} satisfies WishlistItem;

const VIEW: View = {
  id: 3,
  propertyId: "abc",
  address: "49 South Circular Road, Dublin 8",
  viewedAt: "2026-09-27T10:00:00+00:00",
};

describe("Wishlist", () => {
  it("formats a decimal-string price", async () => {
    mockApi({ "GET /me/wishlist": () => [200, [ITEM]] });
    render(<Wishlist />);
    expect(await screen.findByText("€1,700,000 · sold 14 Mar 2025")).toBeInTheDocument();
  });

  it("says when removing fails, and lets the user try again", async () => {
    const answer = deferred<[number, unknown]>();
    const { calls } = mockApi({
      "GET /me/wishlist": () => [200, [ITEM]],
      "DELETE /me/wishlist/7": () => answer.promise,
    });
    render(<Wishlist />);
    const remove = await screen.findByRole("button", { name: `Remove ${ITEM.title}` });
    fireEvent.click(remove);
    fireEvent.click(remove);
    expect(remove).toBeDisabled();
    answer.resolve([503, { title: "Service Unavailable" }]);
    expect(
      await screen.findByText(`Could not remove ${ITEM.title}: Service Unavailable`),
    ).toBeInTheDocument();
    expect(remove).toBeEnabled();
    expect(screen.getByRole("link", { name: ITEM.title })).toBeInTheDocument();
    expect(calls("DELETE /me/wishlist/7")).toBe(1);
  });

  it("says when a note could not be saved", async () => {
    mockApi({
      "GET /me/wishlist": () => [200, [ITEM]],
      "PATCH /me/wishlist/7": () => [
        422,
        {
          title: "Request validation failed",
          errors: [{ loc: ["body", "note"], msg: "Too long", type: "x" }],
        },
      ],
    });
    render(<Wishlist />);
    const note = await screen.findByLabelText(`Note for ${ITEM.title}`);
    fireEvent.change(note, { target: { value: "Near the canal" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Could not save the note: note: Too long")).toBeInTheDocument();
    expect(note).toHaveAttribute("aria-invalid", "true");
  });
});

describe("History", () => {
  it("shows when each property was viewed", async () => {
    mockApi({ "GET /me/history/views": () => [200, [VIEW]] });
    render(<History />);
    expect(await screen.findByText(/27 Sept 2026/)).toBeInTheDocument();
  });

  it("keeps the list and says so when clearing fails", async () => {
    mockApi({
      "GET /me/history/views": () => [200, [VIEW]],
      "DELETE /me/history/views": () => [500, { title: "Internal Server Error" }],
    });
    render(<History />);
    fireEvent.click(await screen.findByRole("button", { name: "Clear all" }));
    expect(
      await screen.findByText("Could not clear your history: Internal Server Error"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: VIEW.address })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Clear all" })).toBeEnabled());
  });
});
