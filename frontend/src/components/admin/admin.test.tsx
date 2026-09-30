import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SessionProvider } from "@/components/auth/session";
import { ReportForm } from "@/components/report/report-form";
import type { RemovalRequest } from "@/lib/api/client";
import { ME, mockApi } from "@/test-fixtures/api";
import summary from "@/test-fixtures/summary-south-circular-road.json";

import { RequireAdmin } from "./common";
import { RemovalRequests } from "./panels";

const nav = vi.hoisted(() => ({ query: "" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.query),
  usePathname: () => "/admin",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

afterEach(() => vi.unstubAllGlobals());

const ADMIN = {
  ...ME,
  roles: ["admin", "user"],
  permissions: [...ME.permissions, "admin:removals", "admin:audit"],
};

const REQUEST: RemovalRequest = {
  id: "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  reference: "R-7C9E6679",
  propertyId: "abc",
  propertyAddress: "49 South Circular Road, Dublin 8",
  propertySuppressed: false,
  submittedAddress: "49 South Circular Road, Dublin 8",
  requesterEmail: "owner@example.ie",
  relationship: "owner",
  reason: "Please hide it",
  requestType: "suppress_display",
  status: "new",
  createdAt: "2026-09-30T10:00:00+00:00",
  decidedBy: null,
  decidedAt: null,
  decisionNote: null,
};

describe("admin pages", () => {
  it("are not shown to an account without the permission", async () => {
    mockApi({ "GET /me": () => [200, ME] });
    render(
      <SessionProvider>
        <RequireAdmin perm="admin:users">
          <p>secret</p>
        </RequireAdmin>
      </SessionProvider>,
    );
    expect(await screen.findByText("Your account cannot use this page.")).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("decide a removal request with a note", async () => {
    let decided = false;
    const { fetch } = mockApi({
      "GET /me": () => [200, ADMIN],
      "GET /admin/removal-requests": () => [
        200,
        { items: decided ? [] : [REQUEST], total: decided ? 0 : 1, page: 1, pageSize: 50 },
      ],
      [`PATCH /admin/removal-requests/${REQUEST.id}`]: () => {
        decided = true;
        return [200, { ...REQUEST, status: "approved" }];
      },
    });
    render(<RemovalRequests />);
    expect(await screen.findByText("Stop showing the address")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Note to the requester/), {
      target: { value: "Done." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve and hide the address" }));
    expect(await screen.findByText("No requests here.")).toBeInTheDocument();
    const patch = fetch.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      status: "approved",
      decisionNote: "Done.",
    });
  });
});

describe("ReportForm", () => {
  it("fills in the property's address and sends the request without the trap field", async () => {
    nav.query = `property=${summary.id}`;
    const { fetch } = mockApi({
      [`GET /properties/${summary.id}/summary`]: () => [200, summary],
      "POST /reports": () => [202, { reference: "R-12345678" }],
    });
    render(<ReportForm />);
    await waitFor(() => expect(screen.getByLabelText("The address")).toHaveValue(summary.address));
    fireEvent.click(screen.getByRole("button", { name: "Send the request" }));
    expect(await screen.findByText("R-12345678")).toBeInTheDocument();
    const post = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    const body = JSON.parse(String(post?.[1]?.body));
    expect(body).toMatchObject({
      propertyId: summary.id,
      address: summary.address,
      requestType: "suppress_display",
      website: null,
    });
  });
});
