import { render, screen } from "@testing-library/react";

import { PSRA_ATTRIBUTION } from "@/lib/attribution";
import { ROUTES } from "@/lib/routes";

import { SiteFooter } from "./site-footer";

describe("SiteFooter", () => {
  it("always shows the PSRA attribution and error disclaimer", () => {
    render(<SiteFooter />);
    expect(screen.getByText(PSRA_ATTRIBUTION)).toBeInTheDocument();
    expect(screen.getByText(/may contain errors/)).toBeInTheDocument();
  });

  it("links to the removal and correction request form", () => {
    render(<SiteFooter />);
    expect(screen.getByRole("link", { name: /request removal/i })).toHaveAttribute(
      "href",
      ROUTES.report.path,
    );
  });
});
