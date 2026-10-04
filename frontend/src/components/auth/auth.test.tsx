import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";

import { api, ApiError } from "@/lib/api/client";
import { ME, mockApi } from "@/test-fixtures/api";

import { AccountMenu } from "./account-menu";
import { safeNext } from "./form";
import { RecordView } from "./record-view";
import { RequireSignIn } from "./require-sign-in";
import { SaveButton } from "./save-button";
import { SessionProvider, useSession } from "./session";

/** The save button once the session check has answered (it is disabled until then). */
async function saveButton() {
  const button = () => screen.getByRole("button", { name: "Save to wishlist" });
  await waitFor(() => expect(button()).toBeEnabled());
  return button();
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("sign-in helpers", () => {
  it("only follows same-site paths after sign-in", () => {
    expect(safeNext("/account/wishlist")).toBe("/account/wishlist");
    expect(safeNext("/account?x=1#y")).toBe("/account?x=1#y");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });

  it("refuses paths a browser would turn into another site", () => {
    // "\" reads as "/", and tabs and newlines are dropped: both make "//evil.example".
    expect(safeNext("/\\evil.example")).toBe("/");
    expect(safeNext("/\t/evil.example")).toBe("/");
    expect(safeNext("/\n/evil.example")).toBe("/");
    expect(safeNext("/%09/evil.example")).toBe("/%09/evil.example");
  });

  it("refuses dot segments that resolve to another site", () => {
    expect(safeNext("/..//evil.example")).toBe("/");
    expect(safeNext("/./..//evil.example/x?y=1")).toBe("/");
    expect(safeNext("/%2e%2e//evil.example")).toBe("/");
    expect(safeNext("/account/../wishlist")).toBe("/wishlist");
  });

  it("asks signed-out users to sign in before saving, and comes back", () => {
    render(<SaveButton propertyId="abc" />);
    expect(screen.getByRole("link", { name: "Sign in to save" })).toHaveAttribute(
      "href",
      "/login?next=%2F",
    );
  });

  it("comes back with the query string too", () => {
    window.history.replaceState(null, "", "/?ids=a,b");
    render(<SaveButton propertyId="abc" />);
    expect(screen.getByRole("link", { name: "Sign in to save" })).toHaveAttribute(
      "href",
      "/login?next=%2F%3Fids%3Da%2Cb",
    );
  });

  it("keeps account pages' content behind sign-in", () => {
    window.history.replaceState(null, "", "/?tab=2");
    render(
      <RequireSignIn>
        <p>secret</p>
      </RequireSignIn>,
    );
    expect(screen.queryByText("secret")).toBeNull();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/login?next=%2F%3Ftab%3D2",
    );
  });
});

describe("API errors", () => {
  it("names the field a validation problem is about", async () => {
    mockApi({
      "POST /auth/register": () => [
        422,
        {
          title: "Request validation failed",
          status: 422,
          errors: [
            {
              loc: ["body", "password"],
              msg: "String should have at least 10 characters",
              type: "x",
            },
          ],
        },
      ],
    });
    const err = await api
      .register({} as Parameters<typeof api.register>[0])
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe("password: String should have at least 10 characters");
    expect((err as ApiError).detail).toBe((err as ApiError).message);
    expect((err as ApiError).field).toBe("password");
  });
});

describe("session", () => {
  it("does not offer sign-in to someone whose session is still being checked", () => {
    mockApi({ "GET /me": () => new Promise(() => {}) });
    render(
      <SessionProvider>
        <SaveButton propertyId="abc" />
      </SessionProvider>,
    );
    expect(screen.queryByRole("link", { name: "Sign in to save" })).toBeNull();
    expect(screen.getByRole("button", { name: "Save to wishlist" })).toBeDisabled();
  });

  it("shows why a save failed", async () => {
    mockApi({
      "GET /me": () => [200, ME],
      "POST /me/wishlist": () => [
        409,
        { title: "Conflict", detail: "A wishlist holds at most 200 items" },
      ],
    });
    render(
      <SessionProvider>
        <SaveButton propertyId="abc" />
      </SessionProvider>,
    );
    fireEvent.click(await saveButton());
    expect(
      await screen.findByText("Could not save: A wishlist holds at most 200 items"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save to wishlist" })).toBeEnabled();
  });

  it("stays signed in when signing out fails", async () => {
    const { calls } = mockApi({
      "GET /me": () => [200, ME],
      "POST /auth/logout": () => [503, { title: "Service Unavailable" }],
    });
    render(
      <SessionProvider>
        <AccountMenu />
      </SessionProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("Could not sign out: Service Unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    // It asked the server again instead of assuming.
    expect(calls("GET /me")).toBe(2);
  });

  it("signs out when the session had already ended", async () => {
    let ended = false;
    mockApi({
      "GET /me": () => (ended ? [401, { title: "Unauthorized" }] : [200, ME]),
      "POST /auth/logout": () => [401, { title: "Unauthorized" }],
    });
    render(
      <SessionProvider>
        <AccountMenu />
      </SessionProvider>,
    );
    ended = true;
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });

  it("re-checks the session when an authenticated call gets a 401", async () => {
    let signedIn = true;
    mockApi({
      "GET /me": () => (signedIn ? [200, ME] : [401, { title: "Unauthorized" }]),
      "POST /me/wishlist": () => [401, { title: "Unauthorized" }],
    });
    render(
      <SessionProvider>
        <AccountMenu />
        <SaveButton propertyId="abc" />
      </SessionProvider>,
    );
    fireEvent.click(await saveButton());
    signedIn = false;
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to save" })).toBeInTheDocument();
  });
});

describe("RecordView", () => {
  // Mounted once the session is known, as on a client-side visit to a property page.
  function PropertyPage() {
    const { me } = useSession();
    return me ? <RecordView propertyId="abc" /> : null;
  }

  it("records a view once, even when Strict Mode runs effects twice", async () => {
    const { calls } = mockApi({
      "GET /me": () => [200, ME],
      "POST /me/history/views": () => [204],
    });
    render(
      <StrictMode>
        <SessionProvider>
          <PropertyPage />
        </SessionProvider>
      </StrictMode>,
    );
    await waitFor(() => expect(calls("POST /me/history/views")).toBe(1));
    await act(async () => {});
    expect(calls("POST /me/history/views")).toBe(1);
  });
});
