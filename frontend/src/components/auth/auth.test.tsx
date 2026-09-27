import { render, screen } from "@testing-library/react";

import { safeNext } from "./form";
import { RequireSignIn } from "./require-sign-in";
import { SaveButton } from "./save-button";

describe("sign-in helpers", () => {
  it("only follows same-site paths after sign-in", () => {
    expect(safeNext("/account/wishlist")).toBe("/account/wishlist");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });

  it("asks signed-out users to sign in before saving, and comes back", () => {
    render(<SaveButton propertyId="abc" />);
    expect(screen.getByRole("link", { name: "Sign in to save" })).toHaveAttribute(
      "href",
      "/login?next=%2F",
    );
  });

  it("keeps account pages' content behind sign-in", () => {
    render(
      <RequireSignIn>
        <p>secret</p>
      </RequireSignIn>,
    );
    expect(screen.queryByText("secret")).toBeNull();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });
});
