import { fireEvent, render, screen } from "@testing-library/react";

import type { PropertyList } from "@/lib/api/client";
import list from "@/test-fixtures/list-south-circular-road.json";

import { SalesList } from "./sales-list";

describe("SalesList", () => {
  it("asks to zoom in at the national view", () => {
    render(<SalesList state={{ status: "zoom" }} onFocusItem={() => {}} onOpenItem={() => {}} />);
    expect(screen.getByText(/Zoom in to a town/)).toBeInTheDocument();
  });

  it("lists the sales in view as buttons that drive the map", () => {
    const [item] = list.items;
    if (!item) throw new Error("fixture has no items");
    const onFocusItem = vi.fn();
    const onOpenItem = vi.fn();
    render(
      <SalesList
        state={{ status: "ok", data: list as PropertyList }}
        onFocusItem={onFocusItem}
        onOpenItem={onOpenItem}
      />,
    );
    expect(
      screen.getByText(`The 3 most recent of ${list.total}. Zoom in or filter to narrow.`),
    ).toBeInTheDocument();
    const first = screen.getByRole("button", { name: /49 South Circular Road/ });
    fireEvent.focus(first);
    expect(onFocusItem).toHaveBeenLastCalledWith(item.id);
    fireEvent.click(first);
    expect(onOpenItem).toHaveBeenCalledWith(item.id);
  });

  it("marks the sale selected on the map", () => {
    const [, second] = list.items;
    if (!second) throw new Error("fixture has too few items");
    render(
      <SalesList
        state={{ status: "ok", data: list as PropertyList }}
        selectedId={second.id}
        onFocusItem={() => {}}
        onOpenItem={() => {}}
      />,
    );
    const current = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-current") === "true");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent(second.address);
  });
});
