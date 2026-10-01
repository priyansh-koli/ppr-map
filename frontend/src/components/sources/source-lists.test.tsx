import { render, screen } from "@testing-library/react";

import { host, InUse, Planned } from "./source-lists";

const PPR = {
  key: "ppr",
  name: "PSRA Residential Property Price Register",
  url: "https://www.propertypriceregister.ie/website/npsra/ppr/npsra-ppr.nsf/Downloads/PPR-ALL.zip/$FILE/PPR-ALL.zip",
  licence: "PSRA re-use terms",
  attribution: "Contains Residential Property Price Register data © PSRA.",
  cadence: "monthly",
  checkedOn: "2026-09-26",
};

describe("source lists", () => {
  it("names a source's site, not its download URL", () => {
    expect(host(PPR.url)).toBe("propertypriceregister.ie");
    expect(host("not a url")).toBe("not a url");
  });

  it("shows each source's credit line, licence and check date", () => {
    render(<InUse sources={[PPR]} />);
    expect(screen.getByText(PPR.attribution)).toBeInTheDocument();
    expect(screen.getByText(/Licence: PSRA re-use terms/)).toBeInTheDocument();
    expect(screen.getByText("Licence checked 26 Sept 2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "propertypriceregister.ie" })).toHaveAttribute(
      "href",
      PPR.url,
    );
  });

  it("does not link planned sources or claim a check date for them", () => {
    render(
      <Planned sources={[{ ...PPR, key: "noise", name: "EPA noise maps", checkedOn: null }]} />,
    );
    expect(screen.getByText(/EPA noise maps/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
