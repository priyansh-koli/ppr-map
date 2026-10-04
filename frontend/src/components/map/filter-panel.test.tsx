import { fireEvent, render, screen } from "@testing-library/react";

import { DEFAULT_FILTERS, type Filters } from "@/lib/filters";

import { FilterPanel } from "./filter-panel";

function panel(filters: Partial<Filters>) {
  const onChange = vi.fn();
  render(
    <FilterPanel
      filters={{ ...DEFAULT_FILTERS, ...filters }}
      onChange={onChange}
      showHexes={false}
      onShowHexes={() => {}}
    />,
  );
  return onChange;
}

const selected = (label: string) =>
  (screen.getByLabelText(label) as HTMLSelectElement).selectedOptions[0]?.textContent;

describe("FilterPanel", () => {
  it("shows an Eircode-area precision as itself, not as exact only", () => {
    panel({ minConfidence: "routing_key" });
    expect(selected("Location precision")).toBe("Eircode area or better");
  });

  it("shows the stop and school distances a search set, and lets them be removed", () => {
    const onChange = panel({ maxStopM: 500, maxSchoolM: 300 });
    expect(selected("Nearest bus, Luas or rail stop")).toBe("Within 500 m");
    // 300 m is not one of the choices, but a URL can carry it: it is shown, not "Any".
    expect(selected("Nearest school")).toBe("Within 300 m");
    fireEvent.change(screen.getByLabelText("Nearest bus, Luas or rail stop"), {
      target: { value: "" },
    });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ maxStopM: null }));
    fireEvent.change(screen.getByLabelText("Nearest school"), { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ maxSchoolM: null }));
  });
});
