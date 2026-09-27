import { renderToStaticMarkup } from "react-dom/server";

import { PSRA_ATTRIBUTION } from "@/lib/attribution";

import RootLayout from "./layout";

describe("RootLayout", () => {
  const html = renderToStaticMarkup(
    <RootLayout>
      <p>page body</p>
    </RootLayout>,
  );

  it("wraps every page in the footer with the PSRA attribution", () => {
    expect(html).toContain("page body");
    expect(html).toContain(PSRA_ATTRIBUTION.replace("&", "&amp;"));
  });

  it("gives the skip-link target a focusable main landmark", () => {
    expect(html).toMatch(/<main id="main" tabindex="-1"/);
  });
});
