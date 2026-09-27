import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";

import { SessionProvider } from "@/components/auth/session";
import { deferred, ME, mockApi } from "@/test-fixtures/api";

import { ForgotPasswordForm, RegisterForm, ResetPasswordForm, VerifyEmail } from "./auth-forms";

const search = vi.hoisted(() => ({ params: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => search.params,
}));

afterEach(() => {
  vi.unstubAllGlobals();
  search.params = new URLSearchParams();
});

describe("VerifyEmail", () => {
  it("spends the link once, even when Strict Mode runs effects twice", async () => {
    search.params = new URLSearchParams("token=t1");
    let used = false;
    const { calls } = mockApi({
      "GET /me": () => [200, ME],
      "POST /auth/verify-email": () => {
        if (used) return [400, { title: "Bad Request", detail: "This link has expired" }];
        used = true;
        return [200, { message: "Your email is confirmed." }];
      },
    });
    render(
      <StrictMode>
        <SessionProvider>
          <VerifyEmail />
        </SessionProvider>
      </StrictMode>,
    );
    expect(await screen.findByText("Your email is confirmed.")).toBeInTheDocument();
    expect(calls("POST /auth/verify-email")).toBe(1);
  });

  it("says a used link is fine when the address is already confirmed", async () => {
    search.params = new URLSearchParams("token=t2");
    mockApi({
      "GET /me": () => [200, ME],
      "POST /auth/verify-email": () => [
        400,
        { title: "Bad Request", detail: "This link has expired or was already used" },
      ],
    });
    render(
      <SessionProvider>
        <VerifyEmail />
      </SessionProvider>,
    );
    expect(await screen.findByText("Your email is already confirmed.")).toBeInTheDocument();
  });

  it("reports a used link for an unconfirmed address", async () => {
    search.params = new URLSearchParams("token=t3");
    mockApi({
      "GET /me": () => [200, { ...ME, emailVerified: false }],
      "POST /auth/verify-email": () => [
        400,
        { title: "Bad Request", detail: "This link has expired or was already used" },
      ],
    });
    render(
      <SessionProvider>
        <VerifyEmail />
      </SessionProvider>,
    );
    expect(
      await screen.findByText("This link has expired or was already used"),
    ).toBeInTheDocument();
  });
});

describe("RegisterForm", () => {
  function fill() {
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Aoife Byrne" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.ie" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "long enough pw" } });
    fireEvent.click(screen.getByLabelText("I am 18 or older."));
    fireEvent.click(screen.getByLabelText(/I accept the/));
  }
  const policies = () => [200, { termsVersion: "1", privacyVersion: "1" }] as [number, unknown];

  it("moves focus to the message that replaces the form", async () => {
    mockApi({
      "GET /auth/policies": policies,
      "POST /auth/register": () => [202, { message: "Check your email to continue." }],
    });
    render(<RegisterForm />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled(),
    );
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    const done = await screen.findByText(/Check your email to continue/);
    expect(done.parentElement).toHaveFocus();
  });

  it("marks the field a validation error is about", async () => {
    mockApi({
      "GET /auth/policies": policies,
      "POST /auth/register": () => [
        422,
        {
          title: "Request validation failed",
          errors: [{ loc: ["body", "password"], msg: "Too short", type: "x" }],
        },
      ],
    });
    render(<RegisterForm />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled(),
    );
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    const message = await screen.findByText("password: Too short");
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(password.getAttribute("aria-describedby")).toContain(message.id);
    expect(screen.getByLabelText("Email")).not.toHaveAttribute("aria-invalid");
  });
});

describe("ForgotPasswordForm", () => {
  it("sends one request however often it is submitted", async () => {
    const answer = deferred<[number, unknown]>();
    const { calls } = mockApi({ "POST /auth/forgot-password": () => answer.promise });
    render(<ForgotPasswordForm />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.ie" } });
    const form = screen.getByRole("button", { name: "Email me a reset link" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
    await act(async () => answer.resolve([202, { message: "A reset link is on its way." }]));
    expect(await screen.findByText("A reset link is on its way.")).toBeInTheDocument();
    expect(calls("POST /auth/forgot-password")).toBe(1);
  });
});

describe("ResetPasswordForm", () => {
  it("marks the confirmation when the passwords differ, and focuses the result", async () => {
    search.params = new URLSearchParams("token=r1");
    mockApi({ "POST /auth/reset-password": () => [200, { message: "Your password is changed." }] });
    render(<ResetPasswordForm />);
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "a long password" },
    });
    fireEvent.change(screen.getByLabelText("New password again"), {
      target: { value: "another password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(screen.getByText("The two passwords are different.")).toBeInTheDocument();
    expect(screen.getByLabelText("New password again")).toHaveAttribute("aria-invalid", "true");

    fireEvent.change(screen.getByLabelText("New password again"), {
      target: { value: "a long password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Set password" }));
    const done = await screen.findByText("Your password is changed.");
    expect(done.parentElement).toHaveFocus();
  });
});
