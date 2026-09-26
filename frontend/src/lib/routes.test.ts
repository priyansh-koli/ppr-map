import { existsSync } from "node:fs";
import { join } from "node:path";

import { ROUTES } from "./routes";

const APP_DIR = join(__dirname, "..", "app");

describe("route registry", () => {
  const routes = Object.entries(ROUTES);

  it.each(routes)("%s has a page file", (_, route) => {
    const dir = route.path === "/" ? APP_DIR : join(APP_DIR, ...route.path.split("/"));
    expect(existsSync(join(dir, "page.tsx"))).toBe(true);
  });

  it("has unique paths", () => {
    const paths = routes.map(([, r]) => r.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("puts every account page behind sign-in and every admin page behind admin", () => {
    for (const [, r] of routes) {
      if (r.path.startsWith("/account")) expect(r.access).toBe("user");
      if (r.path.startsWith("/admin")) expect(r.access).toBe("admin");
    }
  });
});
