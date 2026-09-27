import { act, fireEvent, render, screen } from "@testing-library/react";

import { SessionProvider } from "@/components/auth/session";
import { deferred, ME, mockApi } from "@/test-fixtures/api";

import { AccountSettings } from "./settings";

afterEach(() => vi.unstubAllGlobals());

function renderSettings() {
  return render(
    <SessionProvider>
      <AccountSettings />
    </SessionProvider>,
  );
}

describe("AccountSettings", () => {
  it("stays signed in and says so when signing out everywhere fails", async () => {
    const { calls } = mockApi({
      "GET /me": () => [200, ME],
      "POST /auth/logout-all": () => [503, { title: "Service Unavailable" }],
    });
    renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Sign out on every device" }));
    expect(
      await screen.findByText("Could not sign out everywhere: Service Unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByText(`Signed in as`, { exact: false })).toBeInTheDocument();
    expect(calls("GET /me")).toBe(2);
  });

  it("changes the password once however often it is submitted, and marks a wrong one", async () => {
    const answer = deferred<[number, unknown]>();
    const { calls } = mockApi({
      "GET /me": () => [200, ME],
      "POST /me/password": () => answer.promise,
    });
    renderSettings();
    const current = await screen.findByLabelText("Current password");
    fireEvent.change(current, { target: { value: "old password" } });
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "a new long password" },
    });
    const form = current.closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(screen.getByRole("button", { name: "Changing…" })).toBeDisabled();
    await act(async () =>
      answer.resolve([403, { title: "Forbidden", detail: "The password is wrong" }]),
    );
    expect(await screen.findByText("The password is wrong")).toBeInTheDocument();
    expect(current).toHaveAttribute("aria-invalid", "true");
    expect(calls("POST /me/password")).toBe(1);
  });
});
