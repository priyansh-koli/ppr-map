import { render, waitFor } from "@testing-library/react";

import { ResultsMap } from "./results-map";

const fake = vi.hoisted(() => ({ setTiles: vi.fn(), setData: vi.fn() }));

// Just enough of MapLibre for the component to start (WebGL is not available here).
vi.mock("maplibre-gl", () => {
  class FakeMap {
    on(event: string, cb: () => void) {
      if (event === "load") queueMicrotask(cb);
      return this;
    }
    addControl() {}
    addSource() {}
    addLayer() {}
    getStyle() {
      return { layers: [] };
    }
    getSource(id: string) {
      return id === "sales" ? { setTiles: fake.setTiles } : { setData: fake.setData };
    }
    setFeatureState() {}
    fitBounds() {}
    remove() {}
  }
  return {
    Map: FakeMap,
    NavigationControl: class {},
    setWorkerUrl: () => {},
    getVersion: () => "test",
    addProtocol: () => {},
    removeProtocol: () => {},
  };
});
vi.mock("pmtiles", () => ({ Protocol: class {} }));

describe("ResultsMap", () => {
  it("keeps its tiles while results are hovered (a new circle object each render)", async () => {
    const query = new URLSearchParams("near=53.33,-6.27&radiusM=500&maxStopM=500");
    const props = (hovered: string | null) => ({
      query,
      bbox: null,
      // As the search page passes it: a new object every render.
      circle: { near: "53.33,-6.27", radiusM: 500 },
      version: "v1",
      highlightId: hovered,
      onOpen: () => {},
    });
    const { rerender } = render(<ResultsMap {...props(null)} />);
    await waitFor(() => expect(fake.setTiles).toHaveBeenCalledTimes(1));
    expect(fake.setData).toHaveBeenCalledTimes(1);
    rerender(<ResultsMap {...props("p1")} />);
    rerender(<ResultsMap {...props("p2")} />);
    rerender(<ResultsMap {...props(null)} />);
    expect(fake.setTiles).toHaveBeenCalledTimes(1);
    expect(fake.setData).toHaveBeenCalledTimes(1);
    // A real change of filters or radius still updates them.
    rerender(
      <ResultsMap
        {...props(null)}
        query={new URLSearchParams("near=53.33,-6.27&radiusM=1000")}
        circle={{ near: "53.33,-6.27", radiusM: 1000 }}
      />,
    );
    expect(fake.setTiles).toHaveBeenCalledTimes(2);
    expect(fake.setData).toHaveBeenCalledTimes(2);
  });
});
